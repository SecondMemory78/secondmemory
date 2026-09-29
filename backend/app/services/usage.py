"""Учёт расхода ИИ-операций и суточные лимиты (защита от «разорения на токенах»).

Каждая операция распознавания/расшифровки/агента: сначала проверяем дневной
лимит врача (429 при превышении), затем выполняем и записываем расход.
Лимиты читаются из окружения «вживую», чтобы их можно было менять без перезапуска
и переопределять в тестах.
"""
import os
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlmodel import Session, select, func
from ..models import UsageRecord
from .. import clock

DEFAULT_LIMITS = {"ocr": 50, "stt": 50, "llm": 200}
KIND_LABEL = {"ocr": "Распознавание файлов", "stt": "Расшифровка речи", "llm": "Команды агента"}


def limit_for(kind: str) -> int:
    return int(os.getenv(f"AI_LIMIT_{kind.upper()}", DEFAULT_LIMITS.get(kind, 1000)))


def _day_bounds(d=None):
    d = d or clock.today()
    start = datetime(d.year, d.month, d.day)
    return start, start + timedelta(days=1)


def used_today(s: Session, doctor_id: int, kind: str) -> int:
    start, end = _day_bounds()
    total = s.exec(select(func.coalesce(func.sum(UsageRecord.units), 0)).where(
        UsageRecord.doctor_id == doctor_id, UsageRecord.kind == kind,
        UsageRecord.created_at >= start, UsageRecord.created_at < end)).one()
    return int(total or 0)


def remaining_today(s: Session, doctor_id: int, kind: str) -> int:
    return max(0, limit_for(kind) - used_today(s, doctor_id, kind))


def record(s: Session, doctor_id: int, kind: str, units: int = 1, detail: str = ""):
    s.add(UsageRecord(doctor_id=doctor_id, kind=kind, units=units, detail=detail,
                      created_at=clock.now()))
    s.commit()


def meter(s: Session, doctor_id: int, kind: str, units: int = 1, detail: str = ""):
    """Проверить дневной лимит и учесть расход. Кидает 429 при превышении."""
    limit = limit_for(kind)
    if used_today(s, doctor_id, kind) + units > limit:
        raise HTTPException(429, f"Суточный лимит «{KIND_LABEL.get(kind, kind)}» исчерпан "
                                 f"({limit}/сутки). Попробуйте завтра или обратитесь к администратору.")
    record(s, doctor_id, kind, units, detail)
