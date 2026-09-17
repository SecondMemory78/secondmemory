"""Фото с несколькими пациентами.

Поток: загрузка → разбивка на фрагменты (по пациентам) → проверка личности каждого
фрагмента (логика Задачи 1) → врач назначает фрагменты пациентам → подтверждение
(данные каждого фрагмента уходят В СВОЮ карту) → изображение удаляется.

Приватность: фрагмент пациента B никогда не попадает в карту A. Изображение — только
временно, до подтверждения. Идемпотентность: повтор загрузки с тем же ключом не плодит дубли.
"""
import base64
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..models import PhotoBatch, PhotoFragment, Patient, SourceDocument, Observation
from ..services.ocr import split_photo
from ..services.identity import resolve_identity
from ..services.usage import meter
from ..services.consent import consent_ok
from ..services.visits import resolve_encounter

router = APIRouter(prefix="/api/intake/photo-batch", tags=["multi-photo"])


def _fragment_view(s: Session, f: PhotoFragment) -> dict:
    """Фрагмент + свежая проверка личности (кандидаты), если ещё не назначен."""
    d = {"id": f.id, "region": json.loads(f.region or "{}"),
         "extracted_name": f.extracted_name, "extracted_dob": f.extracted_dob,
         "values": json.loads(f.values_json or "[]"),
         "resolved_patient_id": f.resolved_patient_id, "status": f.status}
    if f.status in ("pending",) and f.extracted_name:
        parts = f.extracted_name.split()
        q = {"last_name": parts[0] if parts else "", "first_name": parts[1] if len(parts) > 1 else "",
             "middle_name": parts[2] if len(parts) > 2 else "",
             "birth_date": None}
        try:
            from datetime import date
            if f.extracted_dob:
                q["birth_date"] = date.fromisoformat(f.extracted_dob)
        except Exception:
            pass
        r = resolve_identity(s, f.doctor_id, q, mode="auto")
        d["identity"] = {"action": r["action"], "candidates": r.get("candidates", [])}
    return d


def _batch_view(s: Session, b: PhotoBatch) -> dict:
    frags = s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == b.id)).all()
    return {"id": b.id, "status": b.status, "has_image": bool(b.image_b64),
            "fragments": [_fragment_view(s, f) for f in frags]}


@router.post("")
async def upload_batch(file: UploadFile = File(None), sim: str = Form(default=""),
                       idempotency_key: str = Header(default=""),
                       s: Session = Depends(get_session)):
    did = current_doctor_id()
    # идемпотентность: тот же ключ → возвращаем существующий пакет, не создаём дубль
    if idempotency_key:
        ex = s.exec(select(PhotoBatch).where(PhotoBatch.doctor_id == did,
                                             PhotoBatch.idempotency_key == idempotency_key)).first()
        if ex:
            return _batch_view(s, ex)

    from ..services.uploads import read_limited
    image_bytes = await read_limited(file)
    sim_list = None
    if sim:
        try:
            sim_list = json.loads(sim)
        except Exception:
            sim_list = None
    fragments = split_photo(image_bytes, sim=sim_list)

    # каждый фрагмент — отдельная «операция распознавания» по учёту расхода
    meter(s, did, "ocr", units=max(1, len(fragments)), detail="photo-batch")

    b = PhotoBatch(doctor_id=did, status="pending", idempotency_key=idempotency_key,
                   image_b64=base64.b64encode(image_bytes).decode() if image_bytes else "")
    s.add(b); s.commit(); s.refresh(b)
    for fr in fragments:
        nm = fr.get("name", {})
        full = " ".join(x for x in [nm.get("last", ""), nm.get("first", ""), nm.get("middle", "")] if x)
        f = PhotoFragment(batch_id=b.id, doctor_id=did, region=json.dumps(fr.get("region", {})),
                          extracted_name=full, extracted_dob=fr.get("birth_date", ""),
                          values_json=json.dumps(fr.get("values", []), ensure_ascii=False))
        s.add(f)
    s.commit()
    return _batch_view(s, b)


@router.get("/{bid}")
def get_batch(bid: int, s: Session = Depends(get_session)):
    b = s.get(PhotoBatch, bid)
    if not b or b.doctor_id != current_doctor_id():
        raise HTTPException(404, "Пакет не найден")
    return _batch_view(s, b)


class AssignIn(BaseModel):
    patient_id: int


@router.post("/{bid}/fragment/{fid}/assign")
def assign_fragment(bid: int, fid: int, body: AssignIn, s: Session = Depends(get_session)):
    did = current_doctor_id()
    f = s.get(PhotoFragment, fid)
    if not f or f.batch_id != bid or f.doctor_id != did:
        raise HTTPException(404, "Фрагмент не найден")
    p = s.get(Patient, body.patient_id)
    if not p or p.doctor_id != did:
        raise HTTPException(404, "Пациент не найден")   # чужого пациента назначить нельзя
    f.resolved_patient_id = p.id
    f.status = "assigned"
    s.add(f); s.commit()
    return _fragment_view(s, f)


@router.post("/{bid}/fragment/{fid}/discard")
def discard_fragment(bid: int, fid: int, s: Session = Depends(get_session)):
    f = s.get(PhotoFragment, fid)
    if f and f.batch_id == bid and f.doctor_id == current_doctor_id():
        f.status = "discarded"; s.add(f); s.commit()
    return {"ok": True}


@router.post("/{bid}/confirm")
def confirm_batch(bid: int, s: Session = Depends(get_session)):
    """Зафиксировать: данные каждого НАЗНАЧЕННОГО фрагмента уходят в СВОЮ карту
    (значения — как pending, требуют подтверждения врачом). Изображение удаляется."""
    did = current_doctor_id()
    b = s.get(PhotoBatch, bid)
    if not b or b.doctor_id != did:
        raise HTTPException(404, "Пакет не найден")
    committed, blocked = [], []
    for f in s.exec(select(PhotoFragment).where(PhotoFragment.batch_id == bid)).all():
        if f.status != "assigned" or not f.resolved_patient_id:
            continue
        pid = f.resolved_patient_id
        if not consent_ok(s, pid):
            blocked.append({"fragment_id": f.id, "patient_id": pid, "reason": "no_consent"})
            continue
        eid, _ = resolve_encounter(s, pid)
        # документ (текст, не фото) + значения как pending в карту ЭТОГО пациента
        s.add(SourceDocument(patient_id=pid, kind="photo", ocr_status="done",
                             encounter_id=eid, image_purged=True,
                             extracted_name=f.extracted_name, extracted_dob=f.extracted_dob))
        for v in json.loads(f.values_json or "[]"):
            if v.get("parameter_code"):
                s.add(Observation(patient_id=pid, encounter_id=eid,
                                  parameter_code=v["parameter_code"], value_num=v.get("value_num"),
                                  unit=v.get("unit", ""), status="pending"))
        f.status = "committed"; s.add(f)
        committed.append({"fragment_id": f.id, "patient_id": pid})
    # изображение больше не нужно — удаляем (минимизация)
    b.image_b64 = ""
    b.status = "confirmed" if not blocked else "pending"
    s.add(b); s.commit()
    return {"committed": committed, "blocked": blocked, "image_deleted": True}


@router.post("/{bid}/discard")
def discard_batch(bid: int, s: Session = Depends(get_session)):
    b = s.get(PhotoBatch, bid)
    if b and b.doctor_id == current_doctor_id():
        b.image_b64 = ""; b.status = "discarded"; s.add(b); s.commit()
    return {"ok": True, "image_deleted": True}
