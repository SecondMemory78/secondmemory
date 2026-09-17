from datetime import datetime, date
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Appointment, Patient
from ..schemas import AppointmentIn

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class AppointmentPatch(BaseModel):
    starts_at: str | None = None      # ISO дата/датавремя — перенос
    reason: str | None = None
    kind: str | None = None


def _view(a, p):
    return {"id": a.id, "patient_id": a.patient_id,
            "patient_name": p.short_name if p else "",
            "starts_at": a.starts_at.isoformat(), "day": a.starts_at.date().isoformat(),
            "time": a.starts_at.strftime("%H:%M"), "kind": a.kind, "reason": a.reason,
            "status": a.status}


@router.patch("/{aid}")
def update_appointment(aid: int, body: AppointmentPatch, s: Session = Depends(get_session)):
    a = s.get(Appointment, aid)
    if not a or a.doctor_id != current_doctor_id():
        raise HTTPException(404, "Приём не найден")
    data = body.model_dump(exclude_unset=True)
    if data.get("starts_at"):
        v = data["starts_at"]
        if len(v) == 10:
            v = v + "T09:00:00"
        a.starts_at = datetime.fromisoformat(v)
    if "reason" in data and data["reason"] is not None:
        a.reason = data["reason"]
    if data.get("kind"):
        a.kind = data["kind"]
    s.add(a); s.commit(); s.refresh(a)
    if data.get("starts_at"):
        from ..services.alerts import set_alerts
        set_alerts(s, a.doctor_id, "appointment", a.id, a.starts_at, kind="appointment")
    return _view(a, s.get(Patient, a.patient_id))


@router.post("")
def create_appointment(body: AppointmentIn, s: Session = Depends(get_session)):
    a = Appointment(doctor_id=current_doctor_id(), patient_id=body.patient_id,
                    starts_at=datetime.fromisoformat(body.starts_at),
                    kind=body.kind, reason=body.reason)
    s.add(a); s.commit(); s.refresh(a)
    from ..services.alerts import set_alerts
    set_alerts(s, a.doctor_id, "appointment", a.id, a.starts_at, kind="appointment")
    p = s.get(Patient, a.patient_id)
    return {"id": a.id, "patient_id": a.patient_id,
            "patient_name": p.short_name if p else "",
            "starts_at": a.starts_at.isoformat(), "day": a.starts_at.date().isoformat(),
            "time": a.starts_at.strftime("%H:%M"), "kind": a.kind, "reason": a.reason}


@router.post("/{aid}/cancel")
def cancel_appointment(aid: int, s: Session = Depends(get_session)):
    a = s.get(Appointment, aid)
    if a:
        a.status = "cancelled"; s.add(a); s.commit()
        from ..services.alerts import set_alerts
        set_alerts(s, a.doctor_id, "appointment", a.id, None)   # None → отменяет будильники
    return {"ok": True}


@router.get("")
def list_appointments(date_from: str, date_to: str, s: Session = Depends(get_session)):
    """Приёмы в диапазоне [date_from, date_to] включительно (YYYY-MM-DD)."""
    d0 = datetime.fromisoformat(date_from)
    d1 = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59)
    rows = s.exec(select(Appointment).where(
        Appointment.doctor_id == current_doctor_id(),
        Appointment.starts_at >= d0, Appointment.starts_at <= d1,
    )).all()
    rows = [a for a in rows if a.status != "cancelled"]
    rows.sort(key=lambda a: a.starts_at)
    out = []
    for a in rows:
        p = s.get(Patient, a.patient_id)
        out.append({
            "id": a.id, "patient_id": a.patient_id,
            "patient_name": p.short_name if p else "",
            "starts_at": a.starts_at.isoformat(),
            "day": a.starts_at.date().isoformat(),
            "time": a.starts_at.strftime("%H:%M"),
            "kind": a.kind, "reason": a.reason, "status": a.status,
        })
    return out
