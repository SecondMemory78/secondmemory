"""Агент команд: превращает фразу (текст или расшифрованный голос) в действие.

Примеры:
  «запиши на среду в 15:00 пациента Иванова»      → создать приём
  «запиши на сегодня вечером заехать в магазин»   → задача-напоминание
  «в заметки: не забыть заказать расходники»       → задача-заметка
  «запись в карту Иванова: жалобы на никтурию»     → заметка в карту пациента

Сейчас классификатор — детерминированный (правила + разбор дат). Позже он
заменяется вызовом YandexGPT с function calling (те же действия как функции),
контракт результата не меняется.
"""
import re
from ..deps import current_doctor_id
from datetime import date, datetime, timedelta
from sqlmodel import Session, select
from ..models import Patient, Appointment, Reminder, Note
from .nlp import parse_reminder
from .. import clock

# «сегодня» — из шва времени

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресень": 6,
}
DAYPARTS = {"утром": "09:00", "днём": "13:00", "днем": "13:00",
            "вечером": "18:00", "ночью": "21:00"}


def route_command(text: str, s: Session) -> dict:
    low = text.lower().strip()

    # 1) правки/запись в карту пациента
    if "карт" in low:
        p = _find_patient(low, s)
        body = re.sub(r".*карт[уые]?\s*(пациента)?\s*[а-яё]*\s*[:\-]?", "", text, count=1, flags=re.I).strip()
        if p:
            n = Note(patient_id=p.id, text=body or text, source="voice")
            s.add(n); s.commit()
            return {"intent": "patient_note", "message": f"Заметка добавлена в карту: {p.short_name}", "patient_id": p.id}
        return {"intent": "patient_note", "message": "Не нашёл пациента для записи в карту — уточните фамилию", "patient_id": None}

    # 2) запись на приём: есть слово «запиши/записать/приём» + пациент + дата
    if any(w in low for w in ["запиши", "записать", "на приём", "на прием", "приём", "прием"]):
        p = _find_patient(low, s)
        when = _resolve_datetime(low)
        if p and when:
            a = Appointment(doctor_id=current_doctor_id(), patient_id=p.id, starts_at=when,
                            kind="repeat", reason="запись голосом")
            s.add(a); s.commit(); s.refresh(a)
            return {"intent": "appointment",
                    "message": f"Записан приём: {p.short_name}, {when.strftime('%d.%m %H:%M')}",
                    "appointment_id": a.id}
        # не хватило данных — но это явно про пациента: если пациент есть, дата не понята
        if p and not when:
            return {"intent": "appointment", "message": f"Кого записать понял ({p.short_name}), а вот когда — уточните дату/время"}
        # иначе падаем в задачу

    # 3) всё остальное — задача/напоминание/заметка (в духе Todoist/Toki)
    clean = re.sub(r"^\s*(в\s+заметки|заметка|напомни( мне)?)\s*[:\-]?\s*", "", text, flags=re.I)
    parsed = parse_reminder(clean)
    due = _override_due(low) or (datetime.fromisoformat(parsed["due_at"]) if parsed["due_at"] else None)
    r = Reminder(doctor_id=current_doctor_id(), title=parsed["title"], due_at=due,
                 kind=parsed["kind"], priority=parsed["priority"],
                 repeat_days=parsed["repeat_days"], labels=parsed["labels"],
                 project=parsed["project"], source="voice")
    s.add(r); s.commit(); s.refresh(r)
    when_txt = due.strftime("%d.%m %H:%M") if due else "без срока"
    return {"intent": "task", "message": f"Задача создана: {r.title} ({when_txt})", "reminder_id": r.id}


def _find_patient(low: str, s: Session):
    pts = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id(), Patient.is_training == False)).all()
    for p in pts:
        # ищем по фамилии (в т.ч. падежные формы: Иванов/Иванова/Иванову)
        stem = p.last_name.lower()[:-1] if len(p.last_name) > 4 else p.last_name.lower()
        if stem in low:
            return p
    return None


def _resolve_datetime(low: str):
    d = None
    base = clock.today()
    if "послезавтра" in low:
        d = base + timedelta(days=2)
    elif "завтра" in low:
        d = base + timedelta(days=1)
    elif "сегодня" in low:
        d = base
    else:
        for name, wd in WEEKDAYS.items():
            if name in low:
                delta = (wd - base.weekday()) % 7
                delta = delta or 7           # «в четверг» = ближайший будущий
                d = base + timedelta(days=delta)
                break
    if d is None:
        return None
    t = _resolve_time(low) or "09:00"
    hh, mm = map(int, t.split(":"))
    return datetime(d.year, d.month, d.day, hh, mm)


def _resolve_time(low: str):
    m = re.search(r"в\s+(\d{1,2})[:.](\d{2})", low)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"в\s+(\d{1,2})\s*(?:час|ч\b)", low)
    if m:
        return f"{int(m.group(1)):02d}:00"
    for word, tm in DAYPARTS.items():
        if word in low:
            return tm
    return None


def _override_due(low: str):
    """Для задач: «сегодня вечером» и т.п. дают дату+время."""
    dt = _resolve_datetime(low)
    return dt
