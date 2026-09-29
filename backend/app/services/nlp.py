"""Разбор естественного языка в структурированное напоминание.

Функционал в духе Todoist/Toki: врач пишет или говорит
«проконтролировать PSA у Иванова через 3 месяца» — получаем заголовок + срок.

Сейчас — простой детерминированный парсер (даты/интервалы). Позже сюда
подключается LLM (РФ-контур) для более свободных формулировок; контракт тот же.
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Any
from .. import clock

_UNITS = {
    "день": 1, "дня": 1, "дней": 1,
    "недел": 7,
    "месяц": 30, "месяца": 30, "месяцев": 30, "мес": 30,
    "год": 365, "года": 365, "лет": 365,
}


def parse_reminder(text: str) -> Dict[str, Any]:
    t = text.strip()
    low = t.lower()
    # срок берём общим разбором русской речи: «на 6 вечера», «через 20 минут»,
    # «в среду в 15». Если срок не назван — оставляем пустым, а не 9:00.
    from .rudate import parse_datetime
    due = parse_datetime(low)

    # повторение: «каждые 3 месяца», «каждый месяц», «раз в 90 дней»,
    # а также наречиями: «ежедневно», «еженедельно», «ежемесячно», «ежегодно»
    repeat_days = None
    rm = re.search(r"(?:кажд\w+|раз в)\s*(\d+)?\s*([а-яё]+)", low)
    if rm:
        n = int(rm.group(1)) if rm.group(1) else 1
        mult = next((v for k, v in _UNITS.items() if rm.group(2).startswith(k)), None)
        if mult:
            repeat_days = n * mult
    if repeat_days is None:
        for word, days in (("ежедневн", 1), ("еженедельн", 7), ("ежемесячн", 30),
                           ("ежегодн", 365), ("ежекварталь", 90)):
            if word in low:
                repeat_days = days
                break
    if repeat_days and due is None:
        due = parse_datetime("завтра") or (clock.now() + timedelta(days=repeat_days))

    # приоритет: «!срочно», «!важно», «!1».. или слова
    priority = 4
    if re.search(r"!\s*1|срочн|немедленн", low):
        priority = 1
    elif re.search(r"!\s*2|важн", low):
        priority = 2
    elif re.search(r"!\s*3", low):
        priority = 3

    # метки и раздел: первый #тег — раздел (как проект в Todoist), остальные — метки
    tags = re.findall(r"#([а-яёa-z0-9]+)", low)
    project = tags[0].capitalize() if tags else "Входящие"
    labels = ",".join(tags[1:])

    kind = "control" if any(w in low for w in ["psa", "пса", "контрол", "анализ"]) else \
        ("call" if any(w in low for w in ["позвон", "звонок", "перезвон"]) else "task")

    # чистим заголовок: служебные метки, командные обороты и уже разобранный срок.
    # «Поставь напоминание на 6 вечера заехать в магазин» → «заехать в магазин».
    title = re.sub(r"\s*#[а-яёА-ЯЁa-zA-Z0-9]+", "", t).strip()
    title = _clean_title(title)

    return {"title": title or t, "due_at": due.isoformat() if due else None,
            "kind": kind, "priority": priority, "repeat_days": repeat_days,
            "labels": labels, "project": project}


# Командные обороты в начале фразы — в названии задачи они лишние
_CMD_PREFIX = re.compile(
    r"^\s*(?:поставь|постав|создай|сделай|добавь|запиши|напомни(?:\s+мне)?|"
    r"нужно|надо|срочн\w*|важн\w*)\s*(?:мне\s+)?"
    r"(?:задачу|напоминание|дело|запись|заметку)?\s*(?:,|:|-|—)?\s*", re.I)

# Уже разобранные указания времени — в названии тоже не нужны
_TIME_WORDS = re.compile(
    r"\b(?:на\s+)?(?:сегодня|завтра|послезавтра|утром|вечером|дн[её]м|ночью|"
    r"в\s+полдень|в\s+полноч[ьи])\b|"
    r"\bчерез\s+\d+\s*[а-яё]+\b|"
    r"\b(?:в|на|к|ко)\s+\d{1,2}(?:[:.\-]\d{2})?\s*(?:час\w*)?"
    r"(?:\s*(?:утра|дня|вечера|ночи))?\b|"
    r"\bв\s+(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b", re.I)


def _clean_title(title: str) -> str:
    """Убирает командную обвязку и срок, оставляя суть дела."""
    out = _CMD_PREFIX.sub("", title, count=1)
    out = _TIME_WORDS.sub(" ", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,.:;-—")
    return out or title.strip()
