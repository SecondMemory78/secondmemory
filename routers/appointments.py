from datetime import datetime, date, timedelta
from ..deps import current_doctor_id
from .. import clock
from ..services.telemetry import log_event
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import Appointment, Patient, AuditEvent
from ..schemas import AppointmentIn

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class AppointmentPatch(BaseModel):
    starts_at: str | None = None      # ISO дата/датавремя — перенос
    reason: str | None = None
    kind: str | None = None
    duration_min: int | None = None


def _end_time(a):
    return a.starts_at + timedelta(minutes=a.duration_min or 20)


def _view(a, p):
    return {"id": a.id, "patient_id": a.patient_id,
            "patient_name": p.short_name if p else "",
            "starts_at": a.starts_at.isoformat(), "day": a.starts_at.date().isoformat(),
            "time": a.starts_at.strftime("%H:%M"), "kind": a.kind, "reason": a.reason,
            "duration_min": a.duration_min or 20,
            "ends_time": _end_time(a).strftime("%H:%M"),
            "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            "rescheduled_from": a.rescheduled_from.isoformat() if a.rescheduled_from else None,
            "reschedule_count": a.reschedule_count or 0,
            "status": a.status}


def _overlaps(s: Session, doctor_id: int, starts_at, duration_min: int, exclude_id=None):
    """Пересекающиеся приёмы в тот же день — ПОДСКАЗКА, не запрет."""
    ends = starts_at + timedelta(minutes=duration_min or 20)
    day0 = starts_at.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = day0 + timedelta(days=1)
    rows = s.exec(select(Appointment).where(
        Appointment.doctor_id == doctor_id,
        Appointment.starts_at >= day0, Appointment.starts_at < day1,
    )).all()
    out = []
    for r in rows:
        if r.id == exclude_id or r.status == "cancelled":
            continue
        if r.starts_at < ends and _end_time(r) > starts_at:
            out.append({"id": r.id, "time": r.starts_at.strftime("%H:%M"),
                        "ends_time": _end_time(r).strftime("%H:%M")})
    return out


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
        new_start = datetime.fromisoformat(v)
        if new_start != a.starts_at:
            # перенос: запоминаем ПЕРВОЕ исходное время и считаем переносы,
            # чтобы было видно «перенесён с 14.10» и что приём «плавает»
            if a.rescheduled_from is None:
                a.rescheduled_from = a.starts_at
            a.reschedule_count = (a.reschedule_count or 0) + 1
            s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="appointment",
                             entity_id=a.id, action="reschedule",
                             detail=f"{a.starts_at.isoformat(timespec='minutes')} → "
                                    f"{new_start.isoformat(timespec='minutes')}"))
        a.starts_at = new_start
    if "reason" in data and data["reason"] is not None:
        a.reason = data["reason"]
    if data.get("kind"):
        a.kind = data["kind"]
    if data.get("duration_min"):
        a.duration_min = max(5, min(int(data["duration_min"]), 480))
    s.add(a); s.commit(); s.refresh(a)
    if data.get("starts_at"):
        from ..services.alerts import set_alerts
        set_alerts(s, a.doctor_id, "appointment", a.id, a.starts_at, kind="appointment")
    return _view(a, s.get(Patient, a.patient_id))


@router.post("")
def create_appointment(body: AppointmentIn, s: Session = Depends(get_session)):
    a = Appointment(doctor_id=current_doctor_id(), patient_id=body.patient_id,
                    starts_at=datetime.fromisoformat(body.starts_at),
                    kind=body.kind, reason=body.reason,
                    duration_min=max(5, min(int(body.duration_min or 20), 480)))
    s.add(a); s.commit(); s.refresh(a)
    from ..services.alerts import set_alerts
    set_alerts(s, a.doctor_id, "appointment", a.id, a.starts_at, kind="appointment")
    p = s.get(Patient, a.patient_id)
    resp = _view(a, p)                    # единая форма ответа — чтобы поля не расходились
    log_event(s, "appointment.created", {"kind": resp["kind"]}, current_doctor_id())
    return resp


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
        out.append(_view(a, s.get(Patient, a.patient_id)))   # единая форма ответа
    return out


class StatusIn(BaseModel):
    status: str                       # done | no_show | planned
    duration_min: int | None = None   # можно поправить фактическую длительность


@router.post("/{aid}/status")
def set_status(aid: int, body: StatusIn, s: Session = Depends(get_session)):
    """Отметить приём: завершён («Завершить приём»), не пришёл, вернуть в план.
    Завершение ставит ended_at по текущему времени — врач жмёт сам, автоматики нет."""
    a = s.get(Appointment, aid)
    if not a or a.doctor_id != current_doctor_id():
        raise HTTPException(404, "Приём не найден")
    if body.status not in ("done", "no_show", "planned"):
        raise HTTPException(400, "Недопустимый статус")
    a.status = body.status
    if body.status == "done":
        a.ended_at = clock.now()
        if body.duration_min:
            a.duration_min = max(5, min(int(body.duration_min), 480))
    else:
        a.ended_at = None
    s.add(a); s.commit(); s.refresh(a)
    log_event(s, "appointment.status", {"status": a.status}, current_doctor_id())
    return _view(a, s.get(Patient, a.patient_id))


@router.get("/conflicts")
def conflicts(starts_at: str, duration_min: int = 20, exclude_id: int | None = None,
              s: Session = Depends(get_session)):
    """Есть ли наложение по времени. Только предупреждение — создавать не мешаем."""
    dt = datetime.fromisoformat(starts_at if len(starts_at) > 10 else starts_at + "T09:00:00")
    items = _overlaps(s, current_doctor_id(), dt, duration_min, exclude_id)
    return {"items": items, "has_conflict": bool(items)}


@router.get("/schedule.pdf")
def schedule_pdf(date_from: str, date_to: str, s: Session = Depends(get_session)):
    """Расписание на день/неделю в PDF — распечатать список приёмов и задач."""
    from fastapi.responses import Response
    from datetime import date as _date, timedelta as _td
    from ..models import Doctor, Reminder
    from ..services.pdf_export import build_schedule_pdf

    did = current_doctor_id()
    d0 = _date.fromisoformat(date_from)
    d1 = _date.fromisoformat(date_to)
    if d1 < d0:
        raise HTTPException(400, "Конечная дата раньше начальной")
    if (d1 - d0).days > 31:
        raise HTTPException(400, "Слишком большой период (максимум 31 день)")

    start = datetime.combine(d0, datetime.min.time())
    end = datetime.combine(d1, datetime.max.time())
    appts = s.exec(select(Appointment).where(
        Appointment.doctor_id == did,
        Appointment.starts_at >= start, Appointment.starts_at <= end,
    )).all()
    tasks = s.exec(select(Reminder).where(
        Reminder.doctor_id == did, Reminder.status == "open",
        Reminder.due_at != None,                                   # noqa: E711
        Reminder.due_at >= start, Reminder.due_at <= end,
    )).all()

    days = []
    cur = d0
    while cur <= d1:
        iso = cur.isoformat()
        day_appts = sorted([a for a in appts if a.starts_at.date() == cur],
                           key=lambda a: a.starts_at)
        day_tasks = sorted([t for t in tasks if t.due_at.date() == cur],
                           key=lambda t: t.due_at)
        days.append({
            "day": iso,
            "appointments": [_view(a, s.get(Patient, a.patient_id)) for a in day_appts],
            "tasks": [{"time": t.due_at.strftime("%H:%M"), "title": t.title} for t in day_tasks],
        })
        cur += _td(days=1)

    doc = s.get(Doctor, did)
    title = "Расписание на день" if d0 == d1 else "Расписание"
    pdf = build_schedule_pdf(days, doctor_name=doc.full_name if doc else "", title=title)
    headers = {"Content-Disposition": f'attachment; filename="schedule_{date_from}_{date_to}.pdf"'}
    return Response(content=pdf, media_type="application/pdf", headers=headers)
