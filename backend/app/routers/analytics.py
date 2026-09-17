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
    week_ago = datetime.utcnow() - timedelta(days=7)
    by_event = Counter(r.event for r in rows)
    last7 = Counter(r.event for r in rows if r.created_at >= week_ago)
    dau = len({r.doctor_id for r in rows if r.created_at >= datetime.utcnow() - timedelta(days=1)})
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
