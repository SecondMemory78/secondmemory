import os
import json
from datetime import datetime, timedelta
from collections import Counter
from fastapi import Request, APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..models import AnalyticsEvent
from ..services.telemetry import log_event
from .. import clock

# ---- приём событий с клиента ----
ingest = APIRouter(prefix="/api/analytics", tags=["analytics"])


class EventIn(BaseModel):
    event: str
    props: dict = {}


@ingest.post("/event")
def track(body: EventIn, s: Session = Depends(get_session)):
    log_event(s, body.event, body.props)
    return {"ok": True}


# ---- админ-панель аналитики (защищена простым токеном) ----
admin = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dev-admin-token")


def _auth(request: Request = None, x_admin_token: str = Header(default="")):
    from ..deps import require_admin
    return require_admin(request=request, x_admin_token=x_admin_token)


@admin.get("/audit")
def admin_audit(limit: int = 200, _: None = Depends(_auth), s: Session = Depends(get_session)):
    """Журнал действий администрации/поддержки (последние действия)."""
    from ..models import AdminAudit
    rows = s.exec(select(AdminAudit).order_by(AdminAudit.id.desc()).limit(limit)).all()
    return [{"action": r.action, "detail": r.detail,
             "at": r.created_at.isoformat()} for r in rows]


@admin.get("/analytics/overview")
def overview(_: None = Depends(_auth), s: Session = Depends(get_session)):
    from ..models import Doctor, Patient, Appointment, Note, Encounter, UsageRecord
    from sqlmodel import func
    from .. import clock

    def cnt(model):
        return int(s.exec(select(func.count()).select_from(model)).one() or 0)

    ai = int(s.exec(select(func.coalesce(func.sum(UsageRecord.units), 0))).one() or 0)
    start = datetime(clock.today().year, clock.today().month, clock.today().day)
    appts_today = int(s.exec(select(func.count()).select_from(Appointment)
                             .where(Appointment.starts_at >= start,
                                    Appointment.starts_at < start + timedelta(days=1))).one() or 0)
    return {"doctors": cnt(Doctor), "patients": cnt(Patient), "appointments": cnt(Appointment),
            "notes": cnt(Note), "encounters": cnt(Encounter), "ai_ops": ai,
            "appointments_today": appts_today}


@admin.get("/analytics/timeseries")
def timeseries(days: int = 30, _: None = Depends(_auth), s: Session = Depends(get_session)):
    from ..models import Patient, Appointment, UsageRecord
    from sqlmodel import func
    from .. import clock
    start = clock.now() - timedelta(days=days)

    def by_day(col, where_col, agg=func.count(), model=None):
        rows = s.exec(select(func.date(col), agg).where(where_col >= start)
                      .group_by(func.date(col))).all()
        return {str(d): int(n) for d, n in rows}

    pat = by_day(Patient.created_at, Patient.created_at)
    appt = by_day(Appointment.starts_at, Appointment.starts_at)
    ai = by_day(UsageRecord.created_at, UsageRecord.created_at, func.coalesce(func.sum(UsageRecord.units), 0))
    ev = by_day(AnalyticsEvent.created_at, AnalyticsEvent.created_at)
    days_set = sorted(set(pat) | set(appt) | set(ai) | set(ev))
    return [{"date": d, "patients": pat.get(d, 0), "appointments": appt.get(d, 0),
             "ai": ai.get(d, 0), "events": ev.get(d, 0)} for d in days_set]


@admin.get("/analytics/summary")
def summary(_: None = Depends(_auth), s: Session = Depends(get_session)):
    rows = s.exec(select(AnalyticsEvent)).all()
    week_ago = clock.now() - timedelta(days=7)
    by_event = Counter(r.event for r in rows)
    last7 = Counter(r.event for r in rows if r.created_at >= week_ago)
    dau = len({r.doctor_id for r in rows if r.created_at >= clock.now() - timedelta(days=1)})
    return {
        "total_events": len(rows),
        "active_doctors_24h": dau,
        "by_event": dict(by_event),
        "last_7_days": dict(last7),
    }


@admin.get("/analytics/events")
def events(limit: int = 100, _: None = Depends(_auth), s: Session = Depends(get_session)):
    rows = s.exec(select(AnalyticsEvent)).all()
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return [{"event": r.event, "props": json.loads(r.props or "{}"),
             "doctor_id": r.doctor_id, "at": r.created_at.isoformat()} for r in rows[:limit]]


@admin.get("/analytics/insights")
def insights(days: int = 30, _: None = Depends(_auth), s: Session = Depends(get_session)):
    """Расширенная сводка для админки: понятные бизнес-метрики, а не сырые счётчики.

    Всё обезличено: считаем врачей и события, без данных пациентов.
    """
    from ..models import Doctor, UsageRecord, Subscription, Patient, Appointment
    from .. import clock
    now = clock.now()
    start = now - timedelta(days=max(7, min(days, 365)))

    doctors = s.exec(select(Doctor)).all()
    real = [d for d in doctors if not d.is_demo]          # демо не мешаем с настоящими
    demo = [d for d in doctors if d.is_demo]

    events = s.exec(select(AnalyticsEvent).where(AnalyticsEvent.created_at >= start)).all()
    active_ids = {e.doctor_id for e in events}
    def active_since(delta):
        return len({e.doctor_id for e in events if e.created_at >= now - delta})

    # удержание: сколько из зарегистрировавшихся за период вообще что-то делали
    new_docs = [d for d in real if d.created_at >= start]
    activated = len([d for d in new_docs if d.id in active_ids])

    subs = s.exec(select(Subscription)).all()
    active_subs = [x for x in subs if x.status == "active" and x.period_end > now]
    by_plan = Counter(x.plan for x in active_subs)

    usage = s.exec(select(UsageRecord).where(UsageRecord.created_at >= start)).all()
    ai_by_kind = Counter(u.kind for u in usage)
    ai_units = sum(u.units for u in usage)

    # глубина использования: сколько врачей довели до реальной работы
    with_patients = len({p.doctor_id for p in s.exec(select(Patient)).all()})
    with_appts = len({a.doctor_id for a in s.exec(select(Appointment)).all()})

    # событий на активного врача — показывает интенсивность, а не только охват
    per_doctor = round(len(events) / len(active_ids), 1) if active_ids else 0

    return {
        "period_days": (now - start).days,
        "doctors": {
            "total": len(real), "demo_sessions": len(demo),
            "new_in_period": len(new_docs), "activated_of_new": activated,
            "active_24h": active_since(timedelta(days=1)),
            "active_7d": active_since(timedelta(days=7)),
            "active_30d": active_since(timedelta(days=30)),
            "with_patients": with_patients, "with_appointments": with_appts,
        },
        "subscriptions": {"active": len(active_subs), "by_plan": dict(by_plan)},
        "ai": {"operations": len(usage), "units": ai_units, "by_kind": dict(ai_by_kind)},
        "engagement": {"events": len(events), "events_per_active_doctor": per_doctor},
    }
