"""Будильники к событиям (задачам/приёмам) — фундамент напоминаний.

Планировщик (services/scheduler.py) периодически зовёт due_alerts() и доставляет их
(пока — в центр уведомлений; Web Push подключится отдельным слоем поверх этого же
механизма, без изменения модели). Здесь — только вычисление и учёт будильников,
без знания о канале доставки.
"""
import json
from datetime import timedelta
from sqlmodel import Session, select
from ..models import ReminderAlert, NotificationPreference
from .. import clock

DEFAULT_OFFSETS = {"appointment": [15], "control": [1440], "task": [15], "call": [30]}


def get_or_create_prefs(s: Session, doctor_id: int) -> NotificationPreference:
    p = s.exec(select(NotificationPreference).where(
        NotificationPreference.doctor_id == doctor_id)).first()
    if not p:
        p = NotificationPreference(doctor_id=doctor_id)
        s.add(p); s.commit(); s.refresh(p)
    return p


def default_offsets_for(s: Session, doctor_id: int, kind: str) -> list[int]:
    p = get_or_create_prefs(s, doctor_id)
    try:
        d = json.loads(p.default_offsets_json)
    except Exception:
        d = DEFAULT_OFFSETS
    return d.get(kind, DEFAULT_OFFSETS.get(kind, [15]))


def set_alerts(s: Session, doctor_id: int, entity_type: str, entity_id: int,
               due_at, offsets: list[int] | None = None, kind: str = "task"):
    """Пересоздаёт будильники события под актуальный due_at/offsets (напр. при переносе
    времени приёма — старые неактуальные будильники отменяются, ставятся новые)."""
    # отменяем прежние неотправленные будильники этого события
    old = s.exec(select(ReminderAlert).where(
        ReminderAlert.entity_type == entity_type, ReminderAlert.entity_id == entity_id,
        ReminderAlert.status == "pending")).all()
    for a in old:
        a.status = "cancelled"; s.add(a)
    if due_at is None:
        s.commit(); return []
    offs = offsets if offsets is not None else default_offsets_for(s, doctor_id, kind)
    created = []
    for m in offs:
        fire_at = due_at - timedelta(minutes=m)
        if fire_at < clock.now():
            continue          # момент уже прошёл — не ставим будильник в прошлое
        a = ReminderAlert(doctor_id=doctor_id, entity_type=entity_type, entity_id=entity_id,
                          offset_minutes=m, fire_at=fire_at)
        s.add(a); created.append(a)
    s.commit()
    return created


def in_quiet_hours(prefs: NotificationPreference, at=None) -> bool:
    h = (at or clock.now()).hour
    start, end = prefs.quiet_hours_start, prefs.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end          # интервал через полночь, напр. 22..7


def due_alerts(s: Session, limit: int = 200):
    """Будильники, которым пора сработать (fire_at <= сейчас), уважая тихие часы —
    в тихие часы откладываем до конца тихого периода (кроме уже просроченных > 1 суток,
    их не прячем совсем, но и не будим ночью зря)."""
    now = clock.now()
    rows = s.exec(select(ReminderAlert).where(
        ReminderAlert.status == "pending", ReminderAlert.fire_at <= now).limit(limit)).all()
    ready = []
    for a in rows:
        prefs = get_or_create_prefs(s, a.doctor_id)
        if in_quiet_hours(prefs, now):
            continue          # подождём до конца тихих часов
        ready.append(a)
    return ready


def due_escalations(s: Session, limit: int = 200):
    """Будильники, отправленные, но не подтверждённые (нет sent_at+escalation прошло) —
    для повторной отправки один раз."""
    now = clock.now()
    rows = s.exec(select(ReminderAlert).where(ReminderAlert.status == "sent").limit(limit)).all()
    out = []
    for a in rows:
        prefs = get_or_create_prefs(s, a.doctor_id)
        if not prefs.escalation_enabled or not a.sent_at:
            continue
        if now >= a.sent_at + timedelta(minutes=prefs.escalation_minutes):
            out.append(a)
    return out
