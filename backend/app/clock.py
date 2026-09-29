"""Шов времени (T3).

Единственный источник «сейчас» и «сегодня» в приложении. Убирает захардкоженную
дату 2026-03-12 из dashboard/assistant/seed.

Таймзона: по умолчанию Europe/Moscow, переопределяется APP_TZ. Таймзона врача
(Doctor.timezone) применяется к тихим часам, дайджесту и сводкам через now_in()/
hour_in() — врач в другом часовом поясе получает их по своему местному времени.
Возвращаем НАИВНОЕ локальное время — весь код сравнивает наивные datetime.

Тесты: время можно зафиксировать через set_fixed()/frozen() и вернуть reset().
Это единственный поддерживаемый способ «промотать» время в тестах — весь код,
идущий через clock.now()/today(), становится детерминированным. Прод оверрайд
не использует (по умолчанию _fixed=None → реальные часы).
"""
import os
import contextlib
from datetime import datetime, date, timedelta

DEFAULT_TZ = os.getenv("APP_TZ", "Europe/Moscow")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(DEFAULT_TZ)
except Exception:
    _TZ = None

# Оверрайд «сейчас» для тестов. None → реальные часы. Наивный datetime.
_fixed: datetime | None = None


def set_fixed(dt: datetime) -> None:
    """Зафиксировать «сейчас» (наивный локальный datetime). Только для тестов."""
    global _fixed
    _fixed = dt.replace(tzinfo=None) if dt.tzinfo else dt


def reset() -> None:
    """Вернуть реальные часы."""
    global _fixed
    _fixed = None


@contextlib.contextmanager
def frozen(dt: datetime):
    """Контекст-менеджер: на время блока «сейчас» = dt, затем восстановить прежнее."""
    global _fixed
    prev = _fixed
    set_fixed(dt)
    try:
        yield
    finally:
        _fixed = prev


def now() -> datetime:
    if _fixed is not None:
        return _fixed
    dt = datetime.now(_TZ) if _TZ else datetime.now()
    return dt.replace(tzinfo=None)


def now_in(tz: str | None) -> datetime:
    """Наивное «сейчас» в таймзоне tz (напр. таймзона врача).

    Если время зафиксировано (тесты) — трактуем фиксированное значение как время в
    ДЕФОЛТНОЙ зоне (APP_TZ) и переводим в tz, чтобы frozen()/set_fixed() оставались
    детерминированными и для мультитаймзонной логики. Пустая/неизвестная tz → now().
    """
    if not tz or tz == DEFAULT_TZ:
        return now()
    try:
        from zoneinfo import ZoneInfo
        target = ZoneInfo(tz)
    except Exception:
        return now()
    if _fixed is not None:
        base = _fixed.replace(tzinfo=_TZ) if _TZ else _fixed
        if base.tzinfo is None:      # нет зоны на сервере — сравнивать не с чем
            return _fixed
        return base.astimezone(target).replace(tzinfo=None)
    return datetime.now(target).replace(tzinfo=None)


def hour_in(tz: str | None) -> int:
    """Текущий час (0..23) в таймзоне tz — для тихих часов, дайджеста, сводок."""
    return now_in(tz).hour


def today() -> date:
    return now().date()


def week_bounds(d: date | None = None):
    """Понедельник и воскресенье недели, содержащей d (по умолчанию — сегодня)."""
    d = d or today()
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)
