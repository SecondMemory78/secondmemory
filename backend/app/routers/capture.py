"""Захват фотографией: направление, бумажка, экран — в дело.

Врач фотографирует направление или памятку и получает ПРЕДЛОЖЕНИЕ: задачу или
запись на приём. Набирать руками не нужно.

Два правила, на которых это держится.

Первое: предложение не становится записью само. Распознавание ошибается в
датах и фамилиях чаще, чем кажется, а задача с неверным сроком хуже, чем её
отсутствие — врач на неё рассчитывает. Поэтому создаём только после нажатия.

Второе: само распознавание идёт фоном. Врач сфотографировал и продолжает
работать, а текст доезжает.
"""
from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, UploadFile)
from sqlmodel import Session, select

from .. import clock
from ..deps import current_doctor_id, get_owned_patient
from ..db import AppSession, get_session
from ..models import Patient, SourceDocument
from ..services.ocr import extract_values
from ..services.telemetry import log_event
from ..services.usage import meter

router = APIRouter(prefix="/api/capture", tags=["capture"])


@router.post("")
async def capture(file: UploadFile = File(None),
                  context_patient_id: int = Form(None),
                  background: BackgroundTasks = None,
                  s: Session = Depends(get_session)):
    """Принять фотографию. Отвечаем сразу, распознаём фоном.

    context_patient_id — чья карта открыта у врача. Это подсказка, а не ответ:
    врачу приносят чужие бумаги прямо на приёме, поэтому открытая карта
    повышает уверенность, но не решает за него.
    """
    from ..services.uploads import read_limited
    meter(s, current_doctor_id(), "ocr", detail="capture")
    image_bytes = await read_limited(file)

    # Контекст кладём в storage_ref: отдельного поля нет, а заводить миграцию
    # ради подсказки не стоит — она живёт до подтверждения врача.
    doc = SourceDocument(patient_id=None, kind="capture", ocr_status="queued",
                         storage_ref=f"ctx:{context_patient_id}" if context_patient_id else "")
    s.add(doc); s.commit(); s.refresh(doc)

    if background is not None:
        background.add_task(_recognize, doc.id, image_bytes, current_doctor_id())
    else:
        _recognize(doc.id, image_bytes, current_doctor_id())

    log_event(s, "capture.queued", {}, current_doctor_id())
    return {"capture_id": doc.id, "ocr_status": "queued",
            "message": "Снимок принят, разбираю. Можно продолжать работу."}


def _recognize(doc_id: int, image_bytes: bytes, doctor_id: int) -> None:
    """Распознавание. Падение не теряем: помечаем в документе."""
    from ..db import AppSession
    # Фоновая задача: контекста запроса уже нет, врача указываем явно.
    with AppSession(scope_doctor_id=doctor_id) as s:
        doc = s.get(SourceDocument, doc_id)
        if not doc:
            return
        try:
            res = extract_values(image_bytes)
            doc.extracted_text = (res.get("text") or "")[:8000]
            doc.ocr_status = "done"
        except Exception as e:                       # noqa: BLE001
            doc.ocr_status = "failed"
            doc.extracted_text = f"Не удалось распознать: {e}"[:500]
        doc.image_purged = True                      # фото не храним, только текст
        s.add(doc); s.commit()


_MEDICAL_WORDS = ("пса", "psa", "креатинин", "гемоглобин", "анализ", "узи",
                  "заключение", "нг/мл", "мкмоль", "результат")


def _looks_medical(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in _MEDICAL_WORDS)


def _proposal(s: Session, text: str, context_patient_id: int | None = None) -> dict:
    """Что предложить по распознанному тексту.

    Разбираем теми же правилами, что и команды ассистента: одна логика на оба
    канала, иначе они разойдутся. Пациента ищем по фамилии из текста, но
    НЕ создаём: тёзки и ошибки распознавания слишком дороги.
    """
    from ..services.assistant import guess_surname
    from ..services.nlp import parse_reminder

    parsed = parse_reminder(text or "")
    out = {"kind": "task", "title": parsed.get("title") or (text or "").strip()[:120],
           "due_at": parsed.get("due_at"), "patient_id": None, "patient_name": "",
           "labels": parsed.get("labels", "")}

    # Открытая карта — сильная подсказка, но врачу приносят и чужие бумаги.
    # Поэтому она только предлагается, подтверждает всегда врач.
    if context_patient_id:
        ctx = s.get(Patient, context_patient_id)
        if ctx and ctx.doctor_id == current_doctor_id():
            out["patient_id"] = ctx.id
            out["patient_name"] = ctx.short_name
            out["patient_from"] = "открытая карта"

    surname = guess_surname(text or "")
    if surname:
        p = s.exec(select(Patient).where(
            Patient.doctor_id == current_doctor_id())).all()
        match = [x for x in p if x.last_name and x.last_name.lower().startswith(surname.lower()[:5])]
        if len(match) == 1:
            if out.get("patient_id") and out["patient_id"] != match[0].id:
                # Открыта одна карта, а в документе другая фамилия — это как раз
                # случай «принесли чужую бумагу». Молчать нельзя.
                out["mismatch"] = {"context": out["patient_name"],
                                   "in_text": match[0].short_name}
            out["patient_id"] = match[0].id
            out["patient_name"] = match[0].short_name
            out["patient_from"] = "фамилия в документе"
        elif len(match) > 1:
            # Тёзки: не выбираем за врача — он укажет сам при подтверждении.
            out["ambiguous_patients"] = [{"id": x.id, "name": x.short_name} for x in match]

    # Дата с ЧАСОМ плюс найденный пациент — похоже на запись на приём.
    # Без часа это задача: «подойти 20 октября» приёмом не является, а
    # поставить его на полночь было бы хуже, чем оставить задачу.
    import re
    has_clock = bool(re.search(r"\b\d{1,2}[:.]\d{2}\b", text or "")
                     or re.search(r"\bв\s+\d{1,2}\s*(час|ч\b)", (text or "").lower()))
    if out["patient_id"] and parsed.get("due_at") and has_clock:
        out["kind"] = "appointment"
    elif _looks_medical(text) and out["patient_id"]:
        out["kind"] = "document"          # медицинский документ в карту пациента
    return out


@router.get("/{capture_id}")
def capture_result(capture_id: int, s: Session = Depends(get_session)):
    doc = s.get(SourceDocument, capture_id)
    if not doc or doc.kind != "capture":
        raise HTTPException(404, "Снимок не найден")
    ctx = None
    if (doc.storage_ref or "").startswith("ctx:"):
        try:
            ctx = int(doc.storage_ref.split(":", 1)[1])
        except ValueError:
            ctx = None
    out = {"capture_id": doc.id, "ocr_status": doc.ocr_status,
           "text": doc.extracted_text or ""}
    if doc.ocr_status == "done":
        out["proposal"] = _proposal(s, doc.extracted_text, ctx)
    return out


@router.post("/{capture_id}/accept")
def accept(capture_id: int, body: dict | None = None,
           s: Session = Depends(get_session)):
    """Создать то, что предложено. Врач мог поправить поля — берём его правку.

    Это единственное место, где из снимка появляется запись: до нажатия в
    базе только распознанный текст.
    """
    doc = s.get(SourceDocument, capture_id)
    if not doc or doc.kind != "capture":
        raise HTTPException(404, "Снимок не найден")
    body = body or {}
    ctx = None
    if (doc.storage_ref or "").startswith("ctx:"):
        try:
            ctx = int(doc.storage_ref.split(":", 1)[1])
        except ValueError:
            ctx = None
    prop = _proposal(s, doc.extracted_text, ctx)
    prop.update({k: v for k, v in body.items() if k in
                 ("kind", "title", "due_at", "patient_id")})

    from datetime import datetime
    from ..services import actions as acts
    from ..services import assistant_actions   # noqa: F401 — регистрирует действия

    when = None
    if prop.get("due_at"):
        try:
            when = datetime.fromisoformat(str(prop["due_at"]))
        except ValueError:
            when = None

    if prop.get("kind") == "document":
        if not prop.get("patient_id"):
            raise HTTPException(400, "Укажите, в чью карту добавить")
        patient = get_owned_patient(s, prop["patient_id"])
        from ..services.parsing import parse_lab_text
        from ..services.visits import active_encounter_id
        from ..models import Observation
        doc.patient_id = patient.id
        doc.kind = "photo"
        doc.encounter_id = active_encounter_id(s, patient.id)
        s.add(doc)
        vals = parse_lab_text(doc.extracted_text or "").get("values", [])
        for v in vals:
            s.add(Observation(patient_id=patient.id, encounter_id=doc.encounter_id,
                              parameter_code=v["parameter_code"],
                              value_num=v.get("value_num"), unit=v.get("unit", ""),
                              source_document_id=doc.id, status="pending",
                              provenance="document", machine_extracted=True))
        s.commit()
        return {"intent": "document", "patient_id": patient.id,
                "message": (f"Документ добавлен в карту: {patient.short_name}. "
                            f"Значений на подтверждение: {len(vals)}" if vals
                            else f"Документ добавлен в карту: {patient.short_name}. "
                                 f"Значений распознать не удалось — текст сохранён")}

    if prop.get("kind") == "appointment":
        if not prop.get("patient_id") or not when:
            raise HTTPException(400, "Для записи на приём нужны пациент и время")
        patient = get_owned_patient(s, prop["patient_id"])
        return acts.run("appointment.create", by="doctor", s=s, patient=patient,
                        when=when, reason="по снимку")

    parsed = {"title": prop.get("title") or "Задача со снимка",
              "kind": "task", "priority": 2, "repeat_days": 0,
              "labels": prop.get("labels", ""), "project": ""}
    return acts.run("task.create", by="doctor", s=s, parsed=parsed, due=when)
