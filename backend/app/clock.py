"""Шов времени (T3).

Единственный источник «сейчас» и «сегодня» в приложении. Убирает захардкоженную
дату 2026-03-12 из dashboard/assistant/seed.

Таймзона: по умолчанию Europe/Moscow, переопределяется APP_TZ; на клиенте таймзона
определяется с устройства и хранится у врача (используется при масштабировании).
Возвращаем НАИВНОЕ локальное время — весь код сравнивает наивные datetime.
"""
import os
from datetime import datetime, date, timedelta

DEFAULT_TZ = os.getenv("APP_TZ", "Europe/Moscow")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(DEFAULT_TZ)
except Exception:
    _TZ = None


def now() -> datetime:
    dt = datetime.now(_TZ) if _TZ else datetime.now()
    return dt.replace(tzinfo=None)


def today() -> date:
    return now().date()


def week_bounds(d: date | None = None):
    """Понедельник и воскресенье недели, содержащей d (по умолчанию — сегодня)."""
    d = d or today()
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)
