"""Планировщик напоминаний (in-process, APScheduler).

ЧЕСТНО: работает корректно, пока сервер ОДИН. При нескольких одновременных копиях
сервера (масштабирование) каждая копия будет иметь свой планировщик и может
задвоить доставку — для этого сценария координационный слой нужно заменить на
общую очередь задач (Celery/RQ + Redis), сама модель данных (ReminderAlert) при
этом не меняется. Сейчас, с одним сервером, дублирования быть не может.

Тик каждую минуту: доставляет готовые будильники (в центр уведомлений; Web Push —
отдельным потребителем поверх того же события), обрабатывает эскалацию (повтор
непрочитанных), и раз в час — утренние дайджесты тем врачам, у кого сейчас их час.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session
from ..db import engine
from .. import clock

log = logging.getLogger("scheduler")
_scheduler = None


def _push_kind_allowed(prefs, kind: str) -> bool:
    """Разрешён ли тип пушем в личных настройках врача."""
    m = {"appointment": prefs.push_appointment, "control": prefs.push_control,
         "task": prefs.push_task, "call": prefs.push_call, "billing": prefs.push_billing}
    return m.get(kind, True)


def _tick():
    from ..models import ReminderAlert, Notification, Reminder
    from .alerts import due_alerts, due_escalations, get_or_create_prefs
    from . import push as push_svc
    try:
        with Session(engine) as s:
            for a in due_alerts(s):
                text = _alert_text(s, a)
                s.add(Notification(doctor_id=a.doctor_id, kind="reminder", level="info",
                                   text=text, dedup_key=f"alert:{a.id}"))
                a.status = "sent"; a.sent_at = clock.now(); s.add(a)
                s.commit()
                # push: тип берём у задачи/приёма, чтобы уважать настройки врача
                prefs = get_or_create_prefs(s, a.doctor_id)
                pkind = "appointment" if a.entity_type == "appointment" else \
                    (s.get(Reminder, a.entity_id).kind if s.get(Reminder, a.entity_id) else "task")
                if _push_kind_allowed(prefs, pkind):
                    push_svc.push_to_doctor(s, a.doctor_id, pkind, "Напоминание", text)
            for a in due_escalations(s):
                text = "Вы ещё не открывали: " + _alert_text(s, a)
                s.add(Notification(doctor_id=a.doctor_id, kind="reminder", level="warn",
                                   text=text, dedup_key=f"alert-esc:{a.id}"))
                a.status = "escalated"; s.add(a); s.commit()
                push_svc.push_to_doctor(s, a.doctor_id, "reminder", "Напоминание", text)
    except Exception:
        log.exception("scheduler tick failed")


def _fmt_offset(m: int) -> str:
    """Человеческое «через 15 минут / 1 час / 1 день»."""
    if m % 1440 == 0:
        d = m // 1440
        from .plural import plural
        return f"через {d} {plural(d, 'день', 'дня', 'дней')}"
    if m % 60 == 0:
        h = m // 60
        from .plural import plural
        return f"через {h} {plural(h, 'час', 'часа', 'часов')}"
    return f"через {m} мин"


def _alert_text(s: Session, a) -> str:
    """Текст будильника. Без диагнозов; название задачи включаем (это не ПДн пациента)."""
    from ..models import Reminder, Appointment
    off = _fmt_offset(a.offset_minutes)
    if a.entity_type == "reminder":
        r = s.get(Reminder, a.entity_id)
        if not r:
            return "Напоминание"
        title = (r.title or "").strip()
        if r.kind == "call":
            return f"Не забудьте: звонок {off}" + (f" — {title}" if title else "")
        return f"{off.capitalize()}: {title}" if title else f"Напоминание {off}"
    if a.entity_type == "appointment":
        ap = s.get(Appointment, a.entity_id)
        t = ap.starts_at.strftime("%H:%M") if ap else ""
        return f"Приём в {t} — {off}"
    return "Напоминание"


def _digest_tick():
    """Раз в час: тем врачам, у кого сейчас час их дайджеста, — одна сводка."""
    from sqlmodel import select
    from ..models import NotificationPreference, Notification
    from ..routers.dashboard import attention as _attention_fn  # переиспользуем «Требуют внимания»
    try:
        with Session(engine) as s:
            now_hour = clock.now().hour
            prefs = s.exec(select(NotificationPreference).where(
                NotificationPreference.digest_enabled == True,
                NotificationPreference.digest_hour == now_hour)).all()
            today = clock.today().isoformat()
            for p in prefs:
                key = f"digest:{p.doctor_id}:{today}"
                exists = s.exec(select(Notification).where(Notification.dedup_key == key)).first()
                if exists:
                    continue
                from ..deps import set_current_doctor_id
                set_current_doctor_id(p.doctor_id)
                data = _attention_fn(s)
                n = data.get("count", 0)
                from .plural import count
                text = (f"Доброе утро! Сегодня требуют внимания {count(n, 'пациент', 'пациента', 'пациентов')}."
                       if n else "Доброе утро! Сегодня всё спокойно — ни одного срочного дела.")
                s.add(Notification(doctor_id=p.doctor_id, kind="digest", level="info",
                                   text=text, dedup_key=key))
                s.commit()
                from . import push as push_svc
                push_svc.push_to_doctor(s, p.doctor_id, "digest", "Доброе утро", text)
            s.commit()
    except Exception:
        log.exception("digest tick failed")


def _recap_tick():
    """Раз в час: сводка по ВЫПОЛНЕННОМУ тем врачам, у кого сейчас их час.
    daily — за сегодня; weekly — за 7 дней, только в выбранный день недели."""
    from sqlmodel import select
    from ..models import NotificationPreference, Notification, Reminder
    from datetime import timedelta
    try:
        with Session(engine) as s:
            now = clock.now()
            prefs = s.exec(select(NotificationPreference).where(
                NotificationPreference.recap_mode != "off",
                NotificationPreference.recap_hour == now.hour)).all()
            for p in prefs:
                if p.recap_mode == "weekly" and now.weekday() != p.recap_weekday:
                    continue
                period_days = 7 if p.recap_mode == "weekly" else 1
                start = now - timedelta(days=period_days)
                tag = "week" if p.recap_mode == "weekly" else clock.today().isoformat()
                key = f"recap:{p.doctor_id}:{tag}:{clock.today().isoformat()}"
                if s.exec(select(Notification).where(Notification.dedup_key == key)).first():
                    continue
                done = s.exec(select(Reminder).where(
                    Reminder.doctor_id == p.doctor_id, Reminder.status == "done",
                    Reminder.completed_at >= start)).all()
                n = len(done)
                from .plural import count
                if p.recap_mode == "weekly":
                    text = (f"За неделю закрыто {count(n, 'задача', 'задачи', 'задач')}."
                            if n else "На этой неделе задачи не закрывались.")
                else:
                    text = (f"Сегодня вы закрыли {count(n, 'задачу', 'задачи', 'задач')}." if n
                            else "Сегодня нет закрытых задач.")
                s.add(Notification(doctor_id=p.doctor_id, kind="recap", level="info",
                                   text=text, dedup_key=key))
                s.commit()
                from . import push as push_svc
                push_svc.push_to_doctor(s, p.doctor_id, "recap", "Вторая память", text)
    except Exception:
        log.exception("recap tick failed")


def start():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_tick, "interval", minutes=1, id="alerts_tick", max_instances=1)
    sched.add_job(_digest_tick, "interval", hours=1, id="digest_tick", max_instances=1)
    sched.add_job(_recap_tick, "interval", hours=1, id="recap_tick", max_instances=1)
    sched.start()
    _scheduler = sched
    return sched


def stop():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
