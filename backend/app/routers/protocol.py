from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..services.consent import require_consent
from ..reference_data import parameter_label
from ..services.visits import active_encounter_id
from ..models import VisitProtocol, Patient, Observation, SafetyItem
from ..schemas import ProtocolIn

router = APIRouter(prefix="/api/patients", tags=["protocol"])

# Читаемые названия параметров для блока «Объективно»


@router.get("/{pid}/protocol")
def get_protocol(pid: int, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    row = s.exec(select(VisitProtocol).where(VisitProtocol.patient_id == pid)).first()
    if row:
        return row.model_dump()
    # черновик, собранный из данных пациента
    return _draft(s, p)


@router.put("/{pid}/protocol")
def save_protocol(pid: int, body: ProtocolIn, s: Session = Depends(get_session)):
    require_consent(s, pid)
    row = s.exec(select(VisitProtocol).where(VisitProtocol.patient_id == pid)).first()
    if row:
        for k, v in body.model_dump().items():
            setattr(row, k, v)
    else:
        row = VisitProtocol(patient_id=pid, encounter_id=active_encounter_id(s, pid), **body.model_dump())
    s.add(row); s.commit(); s.refresh(row)
    return row.model_dump()


def _draft(s: Session, p: Patient):
    # Объективно: последние подтверждённые значения ключевых показателей
    obs = s.exec(select(Observation).where(Observation.patient_id == p.id,
                                           Observation.status == "confirmed")).all()
    latest = {}
    for o in obs:
        if o.value_num is None:
            continue
        cur = latest.get(o.parameter_code)
        if not cur or (o.effective_date or date.min) > (cur.effective_date or date.min):
            latest[o.parameter_code] = o
    parts = []
    for code, o in latest.items():
        parts.append(f"{parameter_label(code)} {o.value_num} {o.unit}".strip())
    objective = ("По данным обследования: " + "; ".join(parts) + ".") if parts else ""

    return {
        "patient_id": p.id,
        "complaints": "",
        "anamnesis_morbi": "",
        "anamnesis_vitae": "",
        "objective": objective,
        "status_localis": "",
        "diagnosis_code": p.diagnosis_code or "",
        "diagnosis_text": p.diagnosis_text or "",
        "recommendations": "",
        "_draft": True,
    }
