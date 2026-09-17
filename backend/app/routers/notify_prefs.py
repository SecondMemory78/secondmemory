"""Настройки уведомлений врача + будильники к событиям."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..models import NotificationPreference, ReminderAlert, Reminder
from ..services.alerts import get_or_create_prefs, set_alerts, DEFAULT_OFFSETS

router = APIRouter(prefix="/api/notify-prefs", tags=["notify-prefs"])


def _view(p: NotificationPreference) -> dict:
    try:
        offsets = json.loads(p.default_offsets_json)
    except Exception:
        offsets = DEFAULT_OFFSETS
    return {"digest_enabled": p.digest_enabled, "digest_hour": p.digest_hour,
            "quiet_hours_start": p.quiet_hours_start, "quiet_hours_end": p.quiet_hours_end,
            "escalation_enabled": p.escalation_enabled, "escalation_minutes": p.escalation_minutes,
            "default_offsets": offsets,
            "push": {"appointment": p.push_appointment, "control": p.push_control,
                     "task": p.push_task, "call": p.push_call, "billing": p.push_billing},
            "recap_mode": p.recap_mode, "recap_hour": p.recap_hour, "recap_weekday": p.recap_weekday,
            "version": p.version}


@router.get("")
def get_prefs(s: Session = Depends(get_session)):
    return _view(get_or_create_prefs(s, current_doctor_id()))


class PrefsPatch(BaseModel):
    expected_version: int
    digest_enabled: Optional[bool] = None
    digest_hour: Optional[int] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    escalation_enabled: Optional[bool] = None
    escalation_minutes: Optional[int] = None
    default_offsets: Optional[dict] = None      # {"appointment":[30,5],...}
    push: Optional[dict] = None                 # {"appointment":true,...}
    recap_mode: Optional[str] = None            # off | daily | weekly
    recap_hour: Optional[int] = None
    recap_weekday: Optional[int] = None


@router.patch("")
def update_prefs(body: PrefsPatch, s: Session = Depends(get_session)):
    p = get_or_create_prefs(s, current_doctor_id())
    if p.version != body.expected_version:
        raise HTTPException(409, "Настройки изменены с другого устройства. Обновите и повторите.")
    data = body.model_dump(exclude_unset=True)
    if data.get("recap_mode") in ("off", "daily", "weekly"):
        p.recap_mode = data["recap_mode"]
    for f in ("digest_enabled", "digest_hour", "quiet_hours_start", "quiet_hours_end",
              "escalation_enabled", "escalation_minutes", "recap_hour", "recap_weekday"):
        if data.get(f) is not None:
            setattr(p, f, data[f])
    if data.get("default_offsets") is not None:
        # валидация: только известные типы, минуты — неотрицательные целые
        clean = {}
        for k, v in data["default_offsets"].items():
            if k in ("appointment", "control", "task", "call") and isinstance(v, list):
                clean[k] = [int(x) for x in v if isinstance(x, (int, float)) and x >= 0][:5]
        p.default_offsets_json = json.dumps(clean or DEFAULT_OFFSETS)
    if data.get("push") is not None:
        pv = data["push"]
        for k, attr in (("appointment", "push_appointment"), ("control", "push_control"),
                        ("task", "push_task"), ("call", "push_call"), ("billing", "push_billing")):
            if k in pv:
                setattr(p, attr, bool(pv[k]))
    p.version += 1
    s.add(p); s.commit(); s.refresh(p)
    return _view(p)


# ── будильники конкретного события ──
alerts_router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@alerts_router.get("/{entity_type}/{entity_id}")
def list_alerts(entity_type: str, entity_id: int, s: Session = Depends(get_session)):
    rows = s.exec(select(ReminderAlert).where(
        ReminderAlert.doctor_id == current_doctor_id(),
        ReminderAlert.entity_type == entity_type, ReminderAlert.entity_id == entity_id,
        ReminderAlert.status.in_(["pending", "sent", "escalated"]))).all()
    return [{"id": a.id, "offset_minutes": a.offset_minutes,
             "fire_at": a.fire_at.isoformat(), "status": a.status} for a in rows]


class SetAlertsIn(BaseModel):
    offsets: list[int]                          # минуты до срока; [] — убрать будильники


@alerts_router.post("/reminder/{rid}")
def set_reminder_alerts(rid: int, body: SetAlertsIn, s: Session = Depends(get_session)):
    """Задать индивидуальные будильники для задачи (переопределяют дефолты)."""
    r = s.get(Reminder, rid)
    if not r or r.doctor_id != current_doctor_id():
        raise HTTPException(404, "Задача не найдена")
    offs = [int(x) for x in body.offsets if x >= 0][:5]
    set_alerts(s, r.doctor_id, "reminder", r.id, r.due_at, offsets=offs, kind=r.kind)
    return list_alerts("reminder", rid, s)
