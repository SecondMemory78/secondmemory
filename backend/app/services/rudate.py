"""Разбор даты и времени так, как говорят врачи.

Принцип: подстраиваемся под речь врача, а не заставляем его говорить
«пятнадцать ноль-ноль». Понимаем «в 3 часа дня», «на 6 вечера», «к 15 часам»,
«через 20 минут», «завтра в полдень», «в среду в 15».

Возвращаем None, если срок не назван, — молча подставлять 9:00 нельзя:
лучше задача без срока, чем задача не на то время.
"""
import re
from datetime import datetime, timedelta

from .. import clock

# Точные формы месяцев. Раньше здесь были корни («ма»), и «в магазин»
# распознавалось как «в мае» — ловушка, которую поймали тесты.
MONTHS = {
    r"январ[яеь]": 1, r"феврал[яеь]": 2, r"март[ае]?": 3, r"апрел[яеь]": 4,
    r"ма[йея]": 5, r"июн[яеь]": 6, r"июл[яеь]": 7, r"август[ае]?": 8,
    r"сентябр[яеь]": 9, r"октябр[яеь]": 10, r"ноябр[яеь]": 11, r"декабр[яеь]": 12,
}

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресен": 6,
}

# «в три часа», «на пять вечера» — числительные словами
WORD_NUMS = {
    "час": 1, "один": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "двадцать один": 21, "двадцать два": 22,
    "двадцать три": 23,
}

_REL_UNITS = [
    (("минут", "мин"), "minutes"),
    (("час",), "hours"),
    (("дня", "день", "дней", "дне"), "days"),
    (("недел",), "weeks"),
    (("месяц",), "months"),
]


def _apply_part_of_day(hour: int, low: str, pos: int) -> int:
    """«3 часа дня» → 15, «6 вечера» → 18, «9 утра» → 9, «3 ночи» → 3."""
    tail = low[pos:pos + 25]                     # смотрим сразу после числа
    if re.search(r"\b(вечер|веч)", tail) and hour < 12:
        return hour + 12
    if re.search(r"\bдня\b|\bдень\b|\bпополудни\b", tail) and hour < 12:
        return hour + 12 if hour >= 1 else hour
    if re.search(r"\b(ноч)", tail):
        return 0 if hour == 12 else hour
    if re.search(r"\b(утр)", tail):
        return 0 if hour == 12 else hour
    return hour


def parse_date(text: str, base):
    """Явная дата: «20 октября», «1 октября 2026», «20.10», «20.10.2026».
    Разбираем ДО времени: иначе «1 октября» прочитается как «в 1 час»."""
    low = (text or "").lower()

    # 20.10 / 20.10.2026 / 20-10
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", low)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3) or 0)
        if yr and yr < 100:
            yr += 2000
        if 1 <= d <= 31 and 1 <= mo <= 12:
            year = yr or base.year
            cand = _safe_date(year, mo, d)
            if cand and not yr and cand < base:
                cand = _safe_date(year + 1, mo, d)     # месяц уже прошёл → следующий год
            if cand:
                return cand, m.span()

    # 20 октября [2026]
    for name, mo in MONTHS.items():
        m = re.search(rf"\b(\d{{1,2}})\s+{name}\w*(?:\s+(\d{{4}}))?", low)
        if m:
            d = int(m.group(1))
            yr = int(m.group(2) or 0)
            year = yr or base.year
            cand = _safe_date(year, mo, d)
            if cand and not yr and cand < base:
                cand = _safe_date(year + 1, mo, d)
            if cand:
                return cand, m.span()

    # просто «в октябре» — первое число месяца
    for name, mo in MONTHS.items():
        m = re.search(rf"\b(?:в|на)\s+{name}\w*\b", low)
        if m:
            cand = _safe_date(base.year, mo, 1)
            if cand and cand < base:
                cand = _safe_date(base.year + 1, mo, 1)
            if cand:
                return cand, m.span()
    return None, None


def _safe_date(year, month, day):
    from datetime import date as _date
    try:
        return _date(year, month, day)
    except ValueError:
        return None


def parse_time(text: str):
    """Вернёт (часы, минуты) или None."""
    low = (text or "").lower()

    if "полдень" in low or "полудня" in low:
        return 12, 0
    if "полноч" in low:
        return 0, 0

    # 15:00 / 15.00 / 15-00
    m = re.search(r"\b(\d{1,2})[:.\-](\d{2})\b", low)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return _apply_part_of_day(hh, low, m.end()), mm

    # «в 15 часов», «на 15 час», «к 15 часам», «в 3 часа дня», «в 15»
    m = re.search(r"(?:^|\b)(?:в|на|к|ко)\s+(\d{1,2})\s*(?:час\w*)?", low)
    if m:
        hh = int(m.group(1))
        if 0 <= hh <= 23:
            return _apply_part_of_day(hh, low, m.end()), 0

    # «15 часов» без предлога
    m = re.search(r"\b(\d{1,2})\s*час\w*", low)
    if m:
        hh = int(m.group(1))
        if 0 <= hh <= 23:
            return _apply_part_of_day(hh, low, m.end()), 0

    # числительные словами: «в три часа дня», «на шесть вечера»
    for word, val in sorted(WORD_NUMS.items(), key=lambda x: -len(x[0])):
        m = re.search(r"(?:^|\b)(?:в|на|к|ко)\s+" + word + r"\b", low)
        if m:
            return _apply_part_of_day(val, low, m.end()), 0

    # время названо только частью суток: «вечером», «утром», «днём»
    if re.search(r"\bвечером\b", low):
        return 18, 0
    if re.search(r"\bутром\b", low):
        return 9, 0
    if re.search(r"\b(дн[её]м|после обеда)\b", low):
        return 14, 0
    if re.search(r"\bноч[ьюи]\b", low):
        return 22, 0
    return None


def parse_relative(text: str):
    """«через 20 минут», «через 2 часа», «через 3 дня» → datetime или None."""
    low = (text or "").lower()
    m = re.search(r"через\s+(\d+)\s*([а-яё]+)", low)
    if not m:
        m2 = re.search(r"через\s+([а-яё]+)\s*([а-яё]*)", low)
        if not m2:
            return None
        n = WORD_NUMS.get(m2.group(1))
        if not n:
            return None
        word = m2.group(2) or m2.group(1)
    else:
        n, word = int(m.group(1)), m.group(2)

    now = clock.now()
    for prefixes, unit in _REL_UNITS:
        if any(word.startswith(p) for p in prefixes):
            if unit == "months":
                return now + timedelta(days=30 * n)
            if unit == "weeks":
                return now + timedelta(weeks=n)
            return now + timedelta(**{unit: n})
    return None


def parse_datetime(text: str):
    """Полная дата-время из фразы. None — срок не назван (не подставляем своё)."""
    low = (text or "").lower()

    rel = parse_relative(low)
    if rel:
        return rel

    base = clock.today()
    day = None

    explicit, span = parse_date(low, base)        # «20 октября», «20.10»
    if explicit:
        day = explicit
        low = (low[:span[0]] + " " + low[span[1]:])   # чтобы «1 октября» не стало «в 1 час»

    if day is not None:
        pass
    elif "послезавтра" in low:
        day = base + timedelta(days=2)
    elif "завтра" in low:
        day = base + timedelta(days=1)
    elif "сегодня" in low or "вечером" in low or "утром" in low:
        day = base
    else:
        for name, wd in WEEKDAYS.items():
            if name in low:
                delta = (wd - base.weekday()) % 7 or 7     # «в среду» — ближайшая будущая
                day = base + timedelta(days=delta)
                break

    hm = parse_time(low)
    if day is None and hm is None:
        return None
    if day is None:                                # названо только время
        day = base
        candidate = datetime(day.year, day.month, day.day, hm[0], hm[1])
        if candidate <= clock.now():               # время уже прошло → завтра
            candidate += timedelta(days=1)
        return candidate
    hh, mm = hm if hm else (9, 0)                  # день назван, время — нет
    return datetime(day.year, day.month, day.day, hh, mm)
