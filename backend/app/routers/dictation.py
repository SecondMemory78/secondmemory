"""Разбор смешанной голосовой записи (Задача 4).

Одна кнопка → расшифровка целиком → разметка на сегменты-намерения → сопоставление
каждого сегмента-пациента с карточкой (логика Задачи 1) → назначение врачом →
подтверждение: заметки уходят в карты пациентов, задачи/звонки становятся напоминаниями,
идеи — во «Входящие». Неоднозначные сегменты ждут выбора врача, в карту ничего не пишется.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..models import Dictation, DictationSegment, Patient, Note, Reminder
from ..services.dictation import segment as segment_text
from ..services.identity import resolve_identity
from ..services.usage import meter
from ..services.consent import consent_ok
from ..services.visits import resolve_encounter
from ..services.nlp import parse_reminder

router = APIRouter(prefix="/api/dictation", tags=["dictation"])


def _seg_view(s: Session, seg: DictationSegment) -> dict:
    d = {"id": seg.id, "seg_type": seg.seg_type, "extracted_name": seg.extracted_name,
         "content": seg.content, "when_text": seg.when_text,
         "resolved_patient_id": seg.resolved_patient_id, "status": seg.status}
    if seg.status == "pending" and seg.seg_type == "patient_note" and seg.extracted_name:
        parts = seg.extracted_name.split()
        q = {"last_name": parts[0] if parts else "", "first_name": parts[1] if len(parts) > 1 else "",
             "middle_name": parts[2] if len(parts) > 2 else "", "birth_date": None}
        r = resolve_identity(s, seg.doctor_id, q, mode="auto")
        d["identity"] = {"action": r["action"], "candidates": r.get("candidates", [])}
    return d


def _view(s: Session, dic: Dictation) -> dict:
    segs = s.exec(select(DictationSegment).where(DictationSegment.dictation_id == dic.id)).all()
    return {"id": dic.id, "status": dic.status, "text": dic.text,
            "segments": [_seg_view(s, x) for x in segs]}


class DictationIn(BaseModel):
    text: str = ""
    sim: list | None = None


@router.post("")
def create_dictation(body: DictationIn, idempotency_key: str = Header(default=""),
                     s: Session = Depends(get_session)):
    """Принимает расшифрованный текст (аудио→текст — на стороне STT, сейчас заглушка).
    Размечает на сегменты и сопоставляет пациентов. Идемпотентно по ключу."""
    did = current_doctor_id()
    if idempotency_key:
        ex = s.exec(select(Dictation).where(Dictation.doctor_id == did,
                                            Dictation.idempotency_key == idempotency_key)).first()
        if ex:
            return _view(s, ex)
    segs = segment_text(body.text, sim=body.sim)
    meter(s, did, "stt", detail="dictation")          # одна расшифровка
    if segs:
        meter(s, did, "llm", units=1, detail="dictation-segment")   # разметка — одна LLM-операция

    dic = Dictation(doctor_id=did, text=body.text, idempotency_key=idempotency_key)
    s.add(dic); s.commit(); s.refresh(dic)
    for seg in segs:
        nm = seg.get("name", {})
        full = " ".join(x for x in [nm.get("last", ""), nm.get("first", ""), nm.get("middle", "")] if x)
        row = DictationSegment(dictation_id=dic.id, doctor_id=did, seg_type=seg.get("seg_type", "note"),
                               extracted_name=full, content=seg.get("content", ""),
                               when_text=seg.get("when_text", ""))
        # авто-привязка пациентского сегмента, если однозначно узнан
        if row.seg_type == "patient_note" and full:
            r = resolve_identity(s, did, {"last_name": nm.get("last", ""), "first_name": nm.get("first", ""),
                                          "middle_name": nm.get("middle", ""), "birth_date": None}, mode="auto")
            if r["action"] == "use":
                row.resolved_patient_id = r["patient_id"]; row.status = "assigned"
        s.add(row)
    s.commit()
    return _view(s, dic)


@router.get("/{did}")
def get_dictation(did: int, s: Session = Depends(get_session)):
    dic = s.get(Dictation, did)
    if not dic or dic.doctor_id != current_doctor_id():
        raise HTTPException(404, "Диктовка не найдена")
    return _view(s, dic)


class AssignIn(BaseModel):
    patient_id: int


@router.post("/{did}/segment/{sid}/assign")
def assign_segment(did: int, sid: int, body: AssignIn, s: Session = Depends(get_session)):
    doc = current_doctor_id()
    seg = s.get(DictationSegment, sid)
    if not seg or seg.dictation_id != did or seg.doctor_id != doc:
        raise HTTPException(404, "Сегмент не найден")
    p = s.get(Patient, body.patient_id)
    if not p or p.doctor_id != doc:
        raise HTTPException(404, "Пациент не найден")
    seg.resolved_patient_id = p.id; seg.status = "assigned"
    s.add(seg); s.commit()
    return _seg_view(s, seg)


@router.post("/{did}/segment/{sid}/discard")
def discard_segment(did: int, sid: int, s: Session = Depends(get_session)):
    seg = s.get(DictationSegment, sid)
    if seg and seg.dictation_id == did and seg.doctor_id == current_doctor_id():
        seg.status = "discarded"; s.add(seg); s.commit()
    return {"ok": True}


@router.post("/{did}/confirm")
def confirm_dictation(did: int, s: Session = Depends(get_session)):
    """Применить сегменты: заметки → в карты пациентов, задачи/звонки → напоминания,
    идеи → во «Входящие». Пациентские сегменты без назначения — пропускаем (ждут выбора)."""
    doc = current_doctor_id()
    dic = s.get(Dictation, did)
    if not dic or dic.doctor_id != doc:
        raise HTTPException(404, "Диктовка не найдена")
    applied, blocked, pending = [], [], []
    for seg in s.exec(select(DictationSegment).where(DictationSegment.dictation_id == did)).all():
        if seg.status in ("committed", "discarded"):
            continue
        if seg.seg_type == "patient_note":
            if not seg.resolved_patient_id:
                pending.append(seg.id); continue          # неоднозначный — ждёт выбора
            if not consent_ok(s, seg.resolved_patient_id):
                blocked.append({"segment_id": seg.id, "reason": "no_consent"}); continue
            eid, _ = resolve_encounter(s, seg.resolved_patient_id)
            s.add(Note(patient_id=seg.resolved_patient_id, encounter_id=eid,
                       text=seg.content, source="voice"))
            seg.status = "committed"; applied.append({"segment_id": seg.id, "as": "note"})
        elif seg.seg_type in ("task", "call"):
            p = parse_reminder((seg.when_text + " " + seg.content).strip())
            due = datetime.fromisoformat(p["due_at"]) if p["due_at"] else None
            s.add(Reminder(doctor_id=doc, title=seg.content or p["title"], due_at=due,
                           patient_id=seg.resolved_patient_id,
                           kind="call" if seg.seg_type == "call" else "task",
                           project="Из диктовки"))
            seg.status = "committed"; applied.append({"segment_id": seg.id, "as": seg.seg_type})
        else:  # idea
            s.add(Reminder(doctor_id=doc, title=seg.content, project="Идеи", kind="task"))
            seg.status = "committed"; applied.append({"segment_id": seg.id, "as": "idea"})
        s.add(seg)
    dic.status = "confirmed" if not pending else "pending"
    s.add(dic); s.commit()
    return {"applied": applied, "blocked": blocked, "pending_choice": pending}


@router.post("/{did}/discard")
def discard_dictation(did: int, s: Session = Depends(get_session)):
    dic = s.get(Dictation, did)
    if dic and dic.doctor_id == current_doctor_id():
        dic.status = "discarded"; s.add(dic); s.commit()
    return {"ok": True}
