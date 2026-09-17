from typing import List
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..services.visits import active_encounter_id
from ..services.consent import consent_ok, require_consent
from ..models import Observation, SafetyItem, Prescription, AuditEvent
from ..schemas import ObservationIn, SafetyIn, PrescriptionIn
from ..services.allergy import check_conflict

router = APIRouter(prefix="/api", tags=["clinical"])

SAFETY_KINDS = ["allergy", "anticoag", "surgery", "chronic", "consent"]


# ---- наблюдения (значения показателей) ----
@router.post("/patients/{pid}/observations")
def add_observation(pid: int, body: ObservationIn, encounter_id: int = None,
                    s: Session = Depends(get_session)):
    require_consent(s, pid)
    from ..services.visits import resolve_encounter, open_encounters
    eid, ambiguous = resolve_encounter(s, pid, encounter_id)
    if ambiguous:
        raise HTTPException(409, {"ambiguous": True, "message": "К какому эпизоду отнести показатель?",
                                  "episodes": [{"id": e.id, "type": e.type, "reason": e.reason,
                                                "ward": e.ward} for e in open_encounters(s, pid)]})
    o = Observation(patient_id=pid, encounter_id=eid, **body.model_dump())
    s.add(o); s.commit(); s.refresh(o)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=o.id,
                     action="create", detail=f"{o.parameter_code}={o.value_num} [{o.status}]"))
    s.commit()
    return o.model_dump()


@router.post("/observations/{oid}/confirm")
def confirm_observation(oid: int, s: Session = Depends(get_session)):
    o = s.get(Observation, oid)
    if not o:
        raise HTTPException(404, "Значение не найдено")
    o.status = "confirmed"; s.add(o)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=o.id,
                     action="confirm", detail="врач подтвердил извлечённое значение"))
    s.commit()
    return o.model_dump()


# ---- блок безопасности ----
@router.get("/patients/{pid}/safety")
def get_safety(pid: int, s: Session = Depends(get_session)):
    rows = {r.kind: r for r in s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid)).all()}
    out = []
    for k in SAFETY_KINDS:
        r = rows.get(k)
        out.append({"kind": k, "state": r.state if r else "unknown", "detail": r.detail if r else ""})
    complete = all(x["state"] != "unknown" for x in out)
    return {"items": out, "complete": complete}


@router.put("/patients/{pid}/safety")
def set_safety(pid: int, body: SafetyIn, s: Session = Depends(get_session)):
    r = s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid,
                                        SafetyItem.kind == body.kind)).first()
    if r:
        r.state, r.detail = body.state, body.detail
    else:
        r = SafetyItem(patient_id=pid, kind=body.kind, state=body.state, detail=body.detail)
    s.add(r)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="safety", entity_id=pid,
                     action="update", detail=f"{body.kind}={body.state}"))
    s.commit()
    return {"kind": r.kind, "state": r.state, "detail": r.detail}


# ---- назначения (с проверкой аллергий) ----
@router.post("/patients/{pid}/prescriptions")
def prescribe(pid: int, body: PrescriptionIn, s: Session = Depends(get_session)):
    if not consent_ok(s, pid):
        raise HTTPException(403, "Нет согласия на обработку ПДн — приём вести нельзя. Оформите согласие.")
    allergies = s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid,
                                                SafetyItem.kind == "allergy")).all()
    conflict = check_conflict(body.drug_name, allergies)
    # Система не блокирует: если конфликт есть и нет причины — вернём предупреждение.
    if conflict and not body.override_reason:
        return {"conflict": True, "saved": False, **conflict}
    p = Prescription(patient_id=pid, encounter_id=active_encounter_id(s, pid),
                     drug_name=body.drug_name, dose=body.dose,
                     regimen=body.regimen, conflict_flag=bool(conflict),
                     override_reason=body.override_reason)
    s.add(p); s.commit(); s.refresh(p)
    detail = f"{p.drug_name}"
    if conflict:
        detail += f" | {conflict['message']} | ПЕРЕОПРЕДЕЛЕНО: {body.override_reason}"
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="prescription", entity_id=p.id,
                     action="create", detail=detail))
    s.commit()
    return {"conflict": bool(conflict), "saved": True, "id": p.id,
            **(conflict or {})}
