"""Производственный календарь.

Субботы и воскресенья приложение вычисляет само — здесь их нет. Здесь только
то, что вычислить нельзя: праздники, переносы и сокращённые дни. Их каждый год
утверждает постановление правительства, поэтому даты вносит человек из
админки, а не «умный» алгоритм.

Главное правило: года нет в базе — приложение показывает только выходные и НЕ
делает вид, что знает про праздники. Ошибиться молча хуже, чем не знать.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import clock
from ..db import get_session
from ..deps import current_doctor_id
from ..models import WorkCalendarDay
from ..services.telemetry import log_event

router = APIRouter(prefix="/api", tags=["workcalendar"])

KINDS = {"holiday", "short", "working"}
MAX_DAYS_PER_YEAR = 400          # год физически не может дать больше


# ── чтение приложением ──────────────────────────────────────────────────────
@router.get("/work-calendar/{year}")
def read_year(year: int, s: Session = Depends(get_session)):
    """Что известно про год. known=false — праздники не заданы, и приложение
    должно показывать только субботы и воскресенья."""
    if not 2000 <= year <= 2100:
        raise HTTPException(400, "Недопустимый год")
    rows = s.exec(select(WorkCalendarDay).where(WorkCalendarDay.year == year)).all()
    return {
        "year": year,
        "known": bool(rows),
        "days": [{"day": r.day.isoformat(), "kind": r.kind, "label": r.label}
                 for r in sorted(rows, key=lambda x: x.day)],
    }


# ── правка из админки ───────────────────────────────────────────────────────
class DayIn(BaseModel):
    day: date
    kind: str = "holiday"
    label: str = ""


class YearIn(BaseModel):
    days: list[DayIn]


# Защита админки — та же, что у остальных её разделов: отдельный токен и
# ограничение по адресам. Своей проверки здесь быть не должно, иначе она
# разойдётся с общей.
from .analytics import _auth as _admin_auth

admin = APIRouter(prefix="/api/admin", tags=["admin"])


@admin.get("/work-calendar/{year}")
def admin_read_year(year: int, _: None = Depends(_admin_auth),
                    s: Session = Depends(get_session)):
    return read_year(year, s)


@admin.put("/work-calendar/{year}")
def admin_write_year(year: int, body: YearIn, _: None = Depends(_admin_auth),
                     s: Session = Depends(get_session)):
    """Заменяет год целиком.

    Принимаем ТОЛЬКО дату, вид и короткую подпись — всё остальное отбрасывается.
    Файл никуда не сохраняется и не исполняется: разбираем и кладём в базу
    числами.
    """
    if not 2000 <= year <= 2100:
        raise HTTPException(400, "Недопустимый год")
    if len(body.days) > MAX_DAYS_PER_YEAR:
        raise HTTPException(400, "Слишком много дат — проверьте, что это один год")

    seen = set()
    rows = []
    for d in body.days:
        if d.day.year != year:
            raise HTTPException(400, f"Дата {d.day} не из {year} года")
        if d.kind not in KINDS:
            raise HTTPException(400, f"Неизвестный вид дня: {d.kind}")
        if d.day in seen:
            continue                     # дубликаты в списке просто пропускаем
        seen.add(d.day)
        rows.append(WorkCalendarDay(year=year, day=d.day, kind=d.kind,
                                    label=(d.label or "")[:120],
                                    updated_by=current_doctor_id_or_none(),
                                    updated_at=clock.now()))

    old = s.exec(select(WorkCalendarDay).where(WorkCalendarDay.year == year)).all()
    for r in old:
        s.delete(r)
    for r in rows:
        s.add(r)
    s.commit()

    log_event(s, "workcalendar.saved", {"year": year, "days": len(rows)}, None)
    return {"year": year, "saved": len(rows)}


def current_doctor_id_or_none():
    """В админке врача в контексте нет — это нормально."""
    try:
        return current_doctor_id()
    except Exception:
        return None
