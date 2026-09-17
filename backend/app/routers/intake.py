from datetime import datetime
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..services.usage import meter
from ..services.consent import require_consent
from ..services.visits import active_encounter_id
from ..models import SourceDocument, Observation, Patient, VisitSession, Note
from ..services.ocr import extract_values
from ..services.stt import transcribe

router = APIRouter(prefix="/api", tags=["intake"])


# ---- загрузка документа: OCR + сверка пациента (защита №1) ----
@router.post("/patients/{pid}/documents")
async def upload_document(pid: int, file: UploadFile = File(None),
                          s: Session = Depends(get_session)):
    require_consent(s, pid)
    meter(s, current_doctor_id(), "ocr", detail="document")
    patient = s.get(Patient, pid)
    if not patient:
        raise HTTPException(404, "Пациент не найден")

    from ..services.uploads import read_limited
    image_bytes = await read_limited(file)
    doc = SourceDocument(patient_id=pid, kind="photo", ocr_status="done",
                         encounter_id=active_encounter_id(s, pid))

    res = extract_values(image_bytes)

    # Защита №1: сверка ФИО/даты рождения из документа с открытой карточкой.
    doc.extracted_name = res.get("extracted_name", "")
    doc.extracted_dob = res.get("extracted_dob", "")
    if doc.extracted_name and patient.last_name.lower() not in doc.extracted_name.lower():
        doc.match_status = "name_mismatch"
    elif doc.extracted_dob and patient.birth_date and doc.extracted_dob != patient.birth_date.isoformat():
        doc.match_status = "dob_mismatch"
    else:
        doc.match_status = "ok"

    # Храним ТЕКСТ, а не фото: изображение не сохраняем на диск, помечаем как очищенное.
    doc.extracted_text = res.get("text", "")
    doc.storage_ref = ""
    doc.image_purged = True

    s.add(doc); s.commit(); s.refresh(doc)

    pending = []
    if doc.match_status == "ok":
        for v in res["values"]:
            o = Observation(patient_id=pid, encounter_id=doc.encounter_id, parameter_code=v["parameter_code"],
                            value_num=v.get("value_num"), value_text=v.get("value_text"),
                            unit=v.get("unit", ""),
                            effective_date=_d(v.get("effective_date")),
                            source_document_id=doc.id, status="pending")
            s.add(o); pending.append(v)
        s.commit()

    return {"document_id": doc.id, "match_status": doc.match_status,
            "extracted_name": doc.extracted_name, "extracted_dob": doc.extracted_dob,
            "image_purged": doc.image_purged, "pending_values": pending}


# ---- голос → текст (для заметок) ----
@router.post("/patients/{pid}/transcribe")
async def transcribe_note(pid: int, save: bool = Form(True),
                          audio: UploadFile = File(None), s: Session = Depends(get_session)):
    require_consent(s, pid)
    meter(s, current_doctor_id(), "stt", detail="note")
    data = await audio.read() if audio else b""
    text = transcribe(data)
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
    idle_min = int((datetime.utcnow() - row.last_active_at).total_seconds() // 60)
    return {"active": True, "patient_id": row.patient_id,
            "patient_name": patient.short_name if patient else "",
            "idle_minutes": idle_min}


@router.post("/session/start")
def start_session(patient_id: int = Form(...), s: Session = Depends(get_session)):
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
