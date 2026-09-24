"""Множественные диагнозы пациента (T6).

Основной диагноз кэшируется в Patient.diagnosis_code/text (шапка, срезы, триггеры).
История не затирается: снятый диагноз остаётся со статусом removed.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..services.consent import require_consent
from ..deps import current_doctor_id, get_owned_patient
from ..serialization import dump, dump_all
from ..models import PatientDiagnosis, Patient, AuditEvent

router = APIRouter(prefix="/api/patients", tags=["diagnoses"])


class DiagnosisIn(BaseModel):
    code: str = ""
    title: str = ""
    wording: str = ""
    is_primary: bool = False


def _sync_primary_cache(s: Session, pid: int):
    """Синхронизируем кэш основного диагноза в карточке пациента."""
    p = s.get(Patient, pid)
    prim = s.exec(select(PatientDiagnosis).where(
        PatientDiagnosis.patient_id == pid, PatientDiagnosis.status == "active",
        PatientDiagnosis.is_primary == True)).first()
    p.diagnosis_code = prim.code if prim else ""
    p.diagnosis_text = (prim.wording or prim.title) if prim else ""
    s.add(p)


def _clear_primary(s: Session, pid: int):
    for d in s.exec(select(PatientDiagnosis).where(
            PatientDiagnosis.patient_id == pid, PatientDiagnosis.is_primary == True)).all():
        d.is_primary = False; s.add(d)


@router.get("/{pid}/diagnoses")
def list_diagnoses(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    rows = s.exec(select(PatientDiagnosis).where(PatientDiagnosis.patient_id == pid)).all()
    rows.sort(key=lambda d: (d.status != "active", not d.is_primary, d.created_at))
    return dump_all(rows)


@router.post("/{pid}/diagnoses")
def add_diagnosis(pid: int, body: DiagnosisIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # сначала владелец (чужой/нет → 404), потом согласие
    require_consent(s, pid)
    active = s.exec(select(PatientDiagnosis).where(
        PatientDiagnosis.patient_id == pid, PatientDiagnosis.status == "active")).all()
    primary = body.is_primary or len(active) == 0     # первый диагноз — основной
    if primary:
        _clear_primary(s, pid)
    d = PatientDiagnosis(patient_id=pid, code=body.code, title=body.title,
                         wording=body.wording or body.title, is_primary=primary)
    s.add(d)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="diagnosis",
                     entity_id=pid, action="add", detail=f"{body.code} {body.title}"))
    s.commit(); s.refresh(d)
    _sync_primary_cache(s, pid); s.commit()
    return dump(d)


@router.post("/{pid}/diagnoses/{did}/primary")
def set_primary(pid: int, did: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    d = s.get(PatientDiagnosis, did)
    if not d or d.patient_id != pid or d.status != "active":
        raise HTTPException(404, "Диагноз не найден")
    _clear_primary(s, pid)
    d.is_primary = True; s.add(d)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="diagnosis",
                     entity_id=pid, action="set_primary", detail=d.code))
    s.commit(); _sync_primary_cache(s, pid); s.commit()
    return dump(d)


@router.post("/{pid}/diagnoses/{did}/remove")
def remove_diagnosis(pid: int, did: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    d = s.get(PatientDiagnosis, did)
    if not d or d.patient_id != pid:
        raise HTTPException(404, "Диагноз не найден")
    d.status = "removed"; d.removed_at = datetime.utcnow()
    was_primary = d.is_primary; d.is_primary = False; s.add(d)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="diagnosis",
                     entity_id=pid, action="remove", detail=d.code))
    s.commit()
    # если сняли основной — назначаем основным первый оставшийся активный
    if was_primary:
        nxt = s.exec(select(PatientDiagnosis).where(
            PatientDiagnosis.patient_id == pid, PatientDiagnosis.status == "active")).first()
        if nxt:
            nxt.is_primary = True; s.add(nxt); s.commit()
    _sync_primary_cache(s, pid); s.commit()
    return {"ok": True}
