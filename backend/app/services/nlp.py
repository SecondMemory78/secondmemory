"""Разбор естественного языка в структурированное напоминание.

Функционал в духе Todoist/Toki: врач пишет или говорит
«проконтролировать PSA у Иванова через 3 месяца» — получаем заголовок + срок.

Сейчас — простой детерминированный парсер (даты/интервалы). Позже сюда
подключается LLM (РФ-контур) для более свободных формулировок; контракт тот же.
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Any

_UNITS = {
    "день": 1, "дня": 1, "дней": 1,
    "недел": 7,
    "месяц": 30, "месяца": 30, "месяцев": 30, "мес": 30,
    "год": 365, "года": 365, "лет": 365,
}


def parse_reminder(text: str) -> Dict[str, Any]:
    t = text.strip()
    low = t.lower()
    due = None

    if "завтра" in low:
        due = datetime.utcnow() + timedelta(days=1)
    elif "послезавтра" in low:
        due = datetime.utcnow() + timedelta(days=2)
    elif "сегодня" in low:
        due = datetime.utcnow()
    else:
        m = re.search(r"через\s+(\d+)\s+([а-яё]+)", low)
        if m:
            n = int(m.group(1))
            word = m.group(2)
            mult = next((v for k, v in _UNITS.items() if word.startswith(k)), None)
            if mult:
                due = datetime.utcnow() + timedelta(days=n * mult)

    # повторение: «каждые 3 месяца», «каждый месяц», «раз в 90 дней»
    repeat_days = None
    rm = re.search(r"(?:кажд\w+|раз в)\s*(\d+)?\s*([а-яё]+)", low)
    if rm:
        n = int(rm.group(1)) if rm.group(1) else 1
        mult = next((v for k, v in _UNITS.items() if rm.group(2).startswith(k)), None)
        if mult:
            repeat_days = n * mult
            if due is None:
                due = datetime.utcnow() + timedelta(days=repeat_days)

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

    # чистим заголовок от служебных меток #tag (в т.ч. с заглавными)
    title = re.sub(r"\s*#[а-яёА-ЯЁa-zA-Z0-9]+", "", t).strip()

    return {"title": title or t, "due_at": due.isoformat() if due else None,
            "kind": kind, "priority": priority, "repeat_days": repeat_days,
            "labels": labels, "project": project}
