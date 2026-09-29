"""Центр уведомлений и эскалация.

Генерация: из текущего состояния (просроченные контроли, суточные лимиты) —
без дублей (dedup_key). Эскалация во внешние каналы — отдельным слоем:
- MAX-бот (РФ) — можно с деталями (ФИО/контроль);
- Telegram (иностранный) — ТОЛЬКО обезличенный пинок «откройте приложение»,
  без имён и диагнозов (152-ФЗ).
Без настроенных токенов внешняя доставка не выполняется — только в приложении.
"""
import os
from sqlmodel import Session, select
from ..models import Notification, Reminder, Doctor, Subscription
from .usage import limit_for, used_today, KIND_LABEL
from .billing import active_subscription
from .email import send_email
from .. import clock

KINDS = ["ocr", "stt", "llm"]


def _exists(s: Session, doctor_id: int, key: str) -> bool:
    return s.exec(select(Notification).where(
        Notification.doctor_id == doctor_id, Notification.dedup_key == key)).first() is not None


def _add(s: Session, doctor_id: int, kind, level, text, key, patient_id=None):
    if not _exists(s, doctor_id, key):
        s.add(Notification(doctor_id=doctor_id, kind=kind, level=level, text=text,
                           dedup_key=key, patient_id=patient_id))


def generate(s: Session, doctor_id: int):
    now = clock.now()
    # просроченные контроли/задачи
    overdue = s.exec(select(Reminder).where(
        Reminder.doctor_id == doctor_id, Reminder.status == "open",
        Reminder.due_at.is_not(None), Reminder.due_at < now)).all()
    for r in overdue:
        days = (now - r.due_at).days
        _add(s, doctor_id, "overdue", "warn",
             f"Просрочено: {r.title}" + (f" (на {days} дн.)" if days else ""),
             f"overdue:{r.id}:{r.due_at.date()}", patient_id=r.patient_id)

    # суточные лимиты ИИ
    today = clock.today().isoformat()
    for k in KINDS:
        used, limit = used_today(s, doctor_id, k), limit_for(k)
        if used >= limit:
            _add(s, doctor_id, "limit", "warn",
                 f"Достигнут суточный лимит «{KIND_LABEL[k]}» ({used}/{limit}).", f"limit:{k}:{today}")
        elif limit and used >= 0.8 * limit:
            _add(s, doctor_id, "limit", "info",
                 f"Приближаетесь к суточному лимиту «{KIND_LABEL[k]}» ({used}/{limit}).", f"limitnear:{k}:{today}")

    # истечение подписки: в приложении — ежедневно последние 5 дней; письмом — на 5-й и 3-й день
    sub = active_subscription(s, doctor_id)
    if sub:
        days_left = (sub.period_end.date() - now.date()).days
        if 0 <= days_left <= 5:
            _add(s, doctor_id, "billing", "warn",
                 f"Подписка заканчивается {sub.period_end.strftime('%d.%m.%Y')} "
                 f"(осталось {days_left} дн.)." + (" Автопродление включено." if sub.auto_renew else " Автопродление выключено — продлите вручную."),
                 f"sub_expiry:{sub.id}:{today}")
        doc = s.get(Doctor, doctor_id)
        if days_left == 5 and not sub.reminder5_sent and doc and doc.email:
            send_email(doc.email, "Подписка скоро закончится — Вторая память",
                       f"{doc.full_name}, ваша подписка «Вторая память» заканчивается "
                       f"{sub.period_end.strftime('%d.%m.%Y')} (через 5 дней). "
                       + ("Автопродление включено — спишем автоматически." if sub.auto_renew
                          else "Автопродление выключено — продлите вручную, чтобы не потерять доступ к записи."))
            sub.reminder5_sent = True; s.add(sub)
        if days_left == 3 and not sub.reminder3_sent and doc and doc.email:
            send_email(doc.email, "Подписка заканчивается через 3 дня — Вторая память",
                       f"{doc.full_name}, ваша подписка заканчивается "
                       f"{sub.period_end.strftime('%d.%m.%Y')} (через 3 дня). "
                       + ("Автопродление включено — спишем автоматически." if sub.auto_renew
                          else "Автопродление выключено — продлите вручную, чтобы не потерять доступ к записи."))
            sub.reminder3_sent = True; s.add(sub)
    s.commit()


# ---- эскалация во внешние каналы (RF-безопасно) ----
def escalation_channel(doctor) -> str:
    """Какой канал использовать по настройкам/токенам."""
    if os.getenv("MAX_BOT_TOKEN") and getattr(doctor, "max_chat_id", ""):
        return "max"
    if os.getenv("TELEGRAM_BOT_TOKEN") and getattr(doctor, "tg_chat_id", ""):
        return "telegram"
    return "none"


def escalation_text(notification, channel: str) -> str:
    """MAX (РФ) — с деталями; Telegram — обезличенно (без ПДн)."""
    if channel == "telegram":
        return "«Вторая память»: есть новое уведомление — откройте приложение."
    return notification.text
