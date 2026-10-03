from datetime import datetime
from ..deps import current_doctor_id, get_owned_patient
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session, select
from ..db import AppSession, get_session
from ..services.usage import meter
from ..services.consent import require_consent
from ..services.telemetry import log_event
from ..services.visits import active_encounter_id
from ..models import SourceDocument, Observation, Patient, VisitSession, Note
from ..services.ocr import extract_values
from ..services.stt import transcribe
from .. import clock

router = APIRouter(prefix="/api", tags=["intake"])


# ---- загрузка документа: OCR + сверка пациента (защита №1) ----
@router.post("/patients/{pid}/documents")
async def upload_document(pid: int, file: UploadFile = File(None),
                          background: BackgroundTasks = None,
                          s: Session = Depends(get_session)):
    patient = get_owned_patient(s, pid)          # сначала владелец (чужой/нет → 404)
    require_consent(s, pid)
    meter(s, current_doctor_id(), "ocr", detail="document")

    from ..services.uploads import read_limited
    image_bytes = await read_limited(file)

    doc = SourceDocument(patient_id=pid, kind="photo", ocr_status="queued",
                         encounter_id=active_encounter_id(s, pid))
    s.add(doc); s.commit(); s.refresh(doc)

    # Распознавание идёт ФОНОМ. Раньше врач ждал ответа Яндекса прямо во время
    # приёма — с телефоном в руке, при пациенте. Теперь фотография принята
    # сразу, а значения доезжают в очередь подтверждения.
    if background is not None:
        background.add_task(_recognize, doc.id, pid, image_bytes)
        log_event(s, "document.queued", {}, current_doctor_id())
        return {"document_id": doc.id, "ocr_status": "queued",
                "message": "Фотография принята, распознаю. "
                           "Значения появятся в очереди подтверждения."}

    _recognize(doc.id, pid, image_bytes)          # запасной путь, если фон недоступен
    return document_status(pid, doc.id, s=s)


def _recognize(doc_id: int, pid: int, image_bytes: bytes) -> None:
    """Распознавание документа. Выполняется фоном, со своей сессией.

    Падения здесь не должны ронять запрос врача: он уже получил ответ. Поэтому
    ошибка помечается в документе, а не теряется — врач увидит «не удалось».
    """
    from ..db import AppSession
    # Фоновая задача: контекста запроса уже нет, врача указываем явно.
    with AppSession(scope_doctor_id=_doctor_for_pid(pid)) as s:
        doc = s.get(SourceDocument, doc_id)
        if not doc:
            return
        try:
            res = extract_values(image_bytes)
        except Exception as e:                    # noqa: BLE001
            doc.ocr_status = "failed"
            doc.extracted_text = f"Не удалось распознать: {e}"[:500]
            s.add(doc); s.commit()
            return

        patient = s.get(Patient, pid)

        # Защита №1: сверка ФИО/даты рождения из документа с открытой карточкой.
        doc.extracted_name = res.get("extracted_name", "")
        doc.extracted_dob = res.get("extracted_dob", "")
        if doc.extracted_name and patient and patient.last_name.lower() not in doc.extracted_name.lower():
            doc.match_status = "name_mismatch"
        elif (doc.extracted_dob and patient and patient.birth_date
              and doc.extracted_dob != patient.birth_date.isoformat()):
            doc.match_status = "dob_mismatch"
        else:
            doc.match_status = "ok"

        # Храним ТЕКСТ, а не фото: изображение не сохраняем, помечаем очищенным.
        doc.extracted_text = res.get("text", "")
        # Что НЕ прошло проверку и почему — врач увидит это рядом с документом
        import json as _json
        doc.rejected_json = _json.dumps(res.get("rejected", []), ensure_ascii=False)[:4000]
        doc.findings_json = _json.dumps(
            {"findings": res.get("findings", []), "scales": res.get("scales", [])},
            ensure_ascii=False)[:8000]
        doc.storage_ref = ""
        doc.image_purged = True
        doc.ocr_status = "done"
        s.add(doc)

        if doc.match_status == "ok":
            # Дубликаты. Врач фотографирует один анализ дважды — с двух
            # ракурсов или просто не заметив, что первый уже загрузился. Без
            # проверки в очереди подтверждения появляются два одинаковых
            # значения, и врач подтверждает оба: в карте дубль на ту же дату.
            existing = s.exec(select(Observation).where(
                Observation.patient_id == pid)).all()
            seen_keys = {(o.parameter_code, o.effective_date,
                          None if o.value_num is None else round(o.value_num, 6))
                         for o in existing}
            duplicates = []

            for v in res["values"]:
                key = (v["parameter_code"], _d(v.get("effective_date")),
                       None if v.get("value_num") is None else round(float(v["value_num"]), 6))
                if key in seen_keys:
                    duplicates.append(v["parameter_code"])
                    continue
                seen_keys.add(key)
                s.add(Observation(
                    patient_id=pid, encounter_id=doc.encounter_id,
                    parameter_code=v["parameter_code"],
                    value_num=v.get("value_num"), value_text=v.get("value_text"),
                    unit=v.get("unit", ""), effective_date=_d(v.get("effective_date")),
                    source_document_id=doc.id, status="pending",
                    provenance="document", machine_extracted=True))

            if duplicates:
                # Не прячем: врач должен знать, что документ уже загружали.
                dup = [{"parameter_code": c, "value_num": None,
                        "why": "такое же значение на ту же дату уже есть в карте",
                        "source_span": ""} for c in duplicates]
                try:
                    prev = _json.loads(doc.rejected_json or "[]")
                except Exception:
                    prev = []
                doc.rejected_json = _json.dumps(prev + dup, ensure_ascii=False)[:4000]
                s.add(doc)
        s.commit()


def _doctor_for_pid(pid: int):
    """Врач пациента. Отдельной сессией: нужен ДО открытия рабочей."""
    with AppSession(scope_doctor_id=None) as s:     # разовое чтение по всем
        p = s.get(Patient, pid)
        return p.doctor_id if p else None


@router.get("/patients/{pid}/documents/{doc_id}")
def document_status(pid: int, doc_id: int, s: Session = Depends(get_session)):
    """Распозналось или ещё нет, и что из этого вышло."""
    get_owned_patient(s, pid)
    doc = s.get(SourceDocument, doc_id)
    if not doc or doc.patient_id != pid:
        raise HTTPException(404, "Документ не найден")

    from ..reference_data import parameter_label
    vals = s.exec(select(Observation).where(
        Observation.source_document_id == doc.id)).all()
    mapped = [{"parameter_code": o.parameter_code,
               "label": parameter_label(o.parameter_code),
               "value_num": o.value_num, "unit": o.unit} for o in vals]
    import json as _json
    try:
        rejected = _json.loads(doc.rejected_json or "[]")
    except Exception:
        rejected = []
    from ..services.findings import human as finding_line
    try:
        blob = _json.loads(doc.findings_json or "[]")
    except Exception:
        blob = []
    # Старые документы хранят просто список находок, новые — объект со шкалами
    if isinstance(blob, dict):
        findings, scales = blob.get("findings", []), blob.get("scales", [])
    else:
        findings, scales = blob, []
    for f in findings:
        f["line"] = finding_line(f)

    return {"document_id": doc.id, "ocr_status": doc.ocr_status,
            "match_status": doc.match_status,
            "rejected": rejected,
            "findings": findings,
            "scales": scales,
            "recognized_text": (doc.extracted_text or "")[:8000],
            "mapped": mapped,
            "extracted_name": doc.extracted_name, "extracted_dob": doc.extracted_dob,
            "image_purged": doc.image_purged,
            "pending_values": mapped}


# ---- голос → текст (для заметок) ----
@router.post("/patients/{pid}/transcribe")
async def transcribe_note(pid: int, save: bool = Form(True),
                          audio: UploadFile = File(None), audio_format: str = Form(""),
                          s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                     # сначала владелец (чужой/нет → 404)
    require_consent(s, pid)
    meter(s, current_doctor_id(), "stt", detail="note")
    data = await audio.read() if audio else b""
    text = transcribe(data, audio_format)
    if save:
        n = Note(patient_id=pid, encounter_id=active_encounter_id(s, pid), text=text, source="voice")
        s.add(n); s.commit()
    return {"text": text}


# ---- сессия приёма (защита №2: продолжить с тем же пациентом?) ----
@router.get("/session/active")
def active_session(s: Session = Depends(get_session)):
    row = s.exec(select(VisitSession).where(VisitSession.doctor_id == current_doctor_id(),
                                            VisitSession.status.in_(["active", "paused"]))).first()
    if not row:
        return {"active": False}
    patient = s.get(Patient, row.patient_id)
    idle_min = int((clock.now() - row.last_active_at).total_seconds() // 60)
    return {"active": True, "patient_id": row.patient_id,
            "patient_name": patient.short_name if patient else "",
            "idle_minutes": idle_min}


@router.post("/session/start")
def start_session(patient_id: int = Form(...), s: Session = Depends(get_session)):
    get_owned_patient(s, patient_id)              # сначала владелец (чужой/нет → 404)
    require_consent(s, patient_id)
    # завершаем прежние
    for r in s.exec(select(VisitSession).where(VisitSession.doctor_id == current_doctor_id(),
                                               VisitSession.status != "finished")).all():
        r.status = "finished"; s.add(r)
    vs = VisitSession(doctor_id=current_doctor_id(), patient_id=patient_id)
    s.add(vs); s.commit(); s.refresh(vs)
    return {"session_id": vs.id, "patient_id": patient_id}


def _d(v):
    from datetime import date
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except Exception:
        return None
