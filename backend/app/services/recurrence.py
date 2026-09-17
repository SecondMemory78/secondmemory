"""Повторяемость напоминаний: следующая дата по единице (день/неделя/месяц/год) и интервалу.

Гибко: «каждый день» = day/1, «через 2 дня» = day/2, «каждую неделю» = week/1,
«каждый месяц» = month/1, «каждые 2 месяца» = month/2, «каждый год» = year/1.
Для месяцев/лет аккуратно обходим длину месяца (31 янв + 1 мес → 28/29 фев).
"""
import calendar
from datetime import timedelta

UNITS = ("day", "week", "month", "year")


def _add_months(dt, months):
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)


def next_due(base, unit: str, interval: int = 1, legacy_repeat_days=None):
    """Следующая дата от base. Приоритет — unit/interval; иначе legacy repeat_days.
    Возвращает datetime или None (если повтор не задан)."""
    if base is None:
        return None
    interval = max(1, int(interval or 1))
    if unit == "day":
        return base + timedelta(days=interval)
    if unit == "week":
        return base + timedelta(weeks=interval)
    if unit == "month":
        return _add_months(base, interval)
    if unit == "year":
        return _add_months(base, 12 * interval)
    if legacy_repeat_days:                      # обратная совместимость со старым полем
        return base + timedelta(days=int(legacy_repeat_days))
    return None
