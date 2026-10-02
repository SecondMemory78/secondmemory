"""Утренняя сводка врача.

Что было не так. Дайджест присылал одну строку с числом: «сегодня требуют
внимания трое». Врач читал её и всё равно шёл разбираться, кто именно и
почему — то есть сводка сообщала, что дело есть, но делать его не помогала.
И главное: про сам день она не говорила ничего — ни сколько приёмов, ни во
сколько первый.

Здесь собирается сводка, которая отвечает на вопрос «каким будет мой день»:
расписание, просроченное и кто требует внимания с причиной. Одним куском, из
данных, которые у нас и так есть.
"""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from .. import clock
from ..deps import current_doctor_id
from ..models import Appointment, Patient, Reminder
from .plural import count


def build(s: Session, doctor_id: int | None = None) -> dict:
    """Сводка на сегодня. Возвращает и готовый текст, и части — текст идёт в
    уведомление, части рисуются на экране со ссылками в карты."""
    did = doctor_id or current_doctor_id()
    now = clock.now()
    today = now.date()

    # ── приёмы на сегодня ───────────────────────────────────────────────────
    appts = [a for a in s.exec(select(Appointment).where(
        Appointment.doctor_id == did)).all()
        if a.starts_at.date() == today and a.status != "cancelled"]
    appts.sort(key=lambda a: a.starts_at)

    schedule = []
    for a in appts:
        p = s.get(Patient, a.patient_id)
        schedule.append({
            "appointment_id": a.id,
            "patient_id": a.patient_id,
            "name": p.short_name if p else "—",
            "time": a.starts_at.strftime("%H:%M"),
            "kind": "первичный" if a.kind == "primary" else "повторный",
            "reason": a.reason or "",
            "past": a.starts_at < now,
        })

    # ── просроченное ────────────────────────────────────────────────────────
    overdue = []
    for r in s.exec(select(Reminder).where(
            Reminder.doctor_id == did, Reminder.status == "open")).all():
        if not r.due_at or r.due_at >= now:
            continue
        days = (now.date() - r.due_at.date()).days
        p = s.get(Patient, r.patient_id) if r.patient_id else None
        overdue.append({"reminder_id": r.id, "title": r.title,
                        "patient_id": r.patient_id,
                        "name": p.short_name if p else "",
                        "days": days})
    overdue.sort(key=lambda x: -x["days"])

    # ── требуют внимания: с причиной, а не числом ───────────────────────────
    from ..routers.dashboard import attention as attention_fn
    attn = attention_fn(s)
    needs = []
    for item in (attn.get("items") or [])[:5]:
        reasons = [r.get("text") or r.get("type", "") for r in item.get("reasons", [])]
        needs.append({"patient_id": item.get("patient_id"),
                      "name": item.get("name", ""),
                      "why": "; ".join(x for x in reasons if x)})

    return {
        "date": today.isoformat(),
        "schedule": schedule,
        "overdue": overdue,
        "needs_attention": needs,
        "attention_total": attn.get("count", 0),
        "text": _text(schedule, overdue, attn.get("count", 0)),
    }


def _text(schedule: list, overdue: list, attn_total: int) -> str:
    """Короткий текст для уведомления. Самое важное — первой фразой: день
    читают с заблокированного экрана, до второй строки доходят не всегда."""
    parts = []

    if schedule:
        upcoming = [a for a in schedule if not a["past"]] or schedule
        parts.append(f"Сегодня {count(len(schedule), 'приём', 'приёма', 'приёмов')}"
                     f", первый в {upcoming[0]['time']}")
    else:
        parts.append("Сегодня приёмов нет")

    if overdue:
        worst = overdue[0]
        tail = f", самое давнее — {count(worst['days'], 'день', 'дня', 'дней')}" if worst["days"] else ""
        parts.append(f"просрочено {count(len(overdue), 'дело', 'дела', 'дел')}{tail}")

    if attn_total:
        parts.append(f"требуют внимания {count(attn_total, 'пациент', 'пациента', 'пациентов')}")

    if len(parts) == 1 and not schedule:
        return "Сегодня приёмов нет, просроченного тоже. Спокойный день."
    # Каждая часть — отдельное предложение, значит с заглавной.
    return ". ".join(x[0].upper() + x[1:] for x in parts) + "."
