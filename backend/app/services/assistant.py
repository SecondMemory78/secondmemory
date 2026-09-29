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
from .visits import active_encounter_id
from .. import clock

# «сегодня» — из шва времени

WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресень": 6,
}
DAYPARTS = {"утром": "09:00", "днём": "13:00", "днем": "13:00",
            "вечером": "18:00", "ночью": "21:00"}


# Речь приходит без знаков препинания, а врач часто диктует несколько дел
# подряд: «запиши Иванова на среду в 15 и Петрова на четверг в 10».
_SPLIT_CMD = re.compile(
    r"\s+(?:и|а\s+также|также|потом|затем|ещ[её])\s+(?=(?:запиш|запис|назнач|напомн|"
    r"постав|добав|в\s+карт|создай|сдела))", re.I)


def split_commands(text: str) -> list:
    """Делит фразу на отдельные команды. Одна команда — вернём её же.

    «и» разделяет, только если справа начинается новая команда: либо глагол
    («и запиши…»), либо у второй части есть СВОЙ срок («и Петрова на четверг
    в 10»). Иначе «и» — часть обычной речи, рвать нельзя.
    """
    from .rudate import parse_datetime
    t = (text or "").strip()
    if not t:
        return []

    chunks = [p.strip(" .,;") for p in re.split(r"[;]|(?<=[.!?])\s+", t) if p.strip(" .,;")]
    out = []
    for chunk in chunks:
        pieces = [chunk]
        for m in reversed(list(re.finditer(r"\s+(?:и|а\s+также|также|потом|затем|ещ[её])\s+",
                                           chunk, re.I))):
            head, tail = chunk[:m.start()].strip(" .,;"), chunk[m.end():].strip(" .,;")
            if len(head) < 5 or len(tail) < 5:
                continue
            starts_cmd = bool(_SPLIT_CMD.match(m.group(0) + tail[:1])) or bool(
                re.match(r"^(?:запиш|запис|назнач|напомн|постав|добав|создай|сдела|в\s+карт)",
                         tail, re.I))
            if starts_cmd or (parse_datetime(tail) and parse_datetime(head)):
                # «запиши Иванова… и Петрова…» — во второй части глагола нет,
                # переносим его, иначе она уйдёт в задачи вместо записи на приём
                if not starts_cmd:
                    verb = re.match(r"^\s*(запиш\w*|запис\w*|назнач\w*|напомн\w*|"
                                    r"постав\w*|добав\w*)", head, re.I)
                    if verb:
                        tail = f"{verb.group(1)} {tail}"
                pieces = [head, tail]
                break
        out.extend(pieces)
    return [p for p in out if p] or [t]


def route_command(text: str, s: Session, channel: str = "text") -> dict:
    """Выполняет команду (или несколько подряд) и пишет в журнал ассистента."""
    parts = split_commands(text)
    if len(parts) > 1:
        results = [_run_one(p, s, channel) for p in parts]
        done = [r for r in results if r.get("ok", True)]
        lines = [r.get("message", "") for r in results if r.get("message")]
        return {"intent": "multi", "ok": bool(done), "count": len(results),
                "results": results,
                "message": f"Выполнено команд: {len(done)} из {len(results)}.\n"
                           + "\n".join(f"• {m}" for m in lines)}
    return _run_one(text, s, channel)


def _run_one(text: str, s: Session, channel: str = "text") -> dict:
    """Публичная точка: выполнить команду и записать её в журнал ассистента
    (экран «Что сделал ассистент» у врача). Результат не меняем."""
    res = _route_command(text, s)
    try:
        _log_assistant_action(s, text, res, channel)
    except Exception:
        s.rollback()
    return res


_AREA_BY_INTENT = {"patient_note": "patient", "appointment": "calendar",
                   "task": "tasks", "trigger_denied": "denied"}


def _log_assistant_action(s: Session, text: str, res: dict, channel: str):
    from ..models import AssistantAction
    intent = res.get("intent", "unknown")
    entity_type, entity_id = "", None
    if res.get("appointment_id"):
        entity_type, entity_id = "appointment", res["appointment_id"]
    elif res.get("reminder_id"):
        entity_type, entity_id = "reminder", res["reminder_id"]
    elif res.get("patient_id"):
        entity_type, entity_id = "patient", res["patient_id"]
    s.add(AssistantAction(
        doctor_id=current_doctor_id(), channel=channel,
        area=_AREA_BY_INTENT.get(intent, "unknown"), intent=intent,
        input_text=text, message=res.get("message", ""),
        entity_type=entity_type, entity_id=entity_id,
        ok=res.get("ok", True)))
    s.commit()


def _route_command(text: str, s: Session) -> dict:
    low = text.lower().strip()

    # 0) триггеры/автослежение — ИИ НЕ управляет ими. Только врач вручную.
    #    Явный отказ, никаких действий (по требованию: правила слежения — зона врача).
    TRIGGER_WORDS = ("триггер", "автослежен", "слежени", "правило слежения", "следи за", "отслеживай")
    if any(w in low for w in TRIGGER_WORDS):
        return {"intent": "trigger_denied",
                "ok": False,
                "message": "Триггеры (автослежение) настраивает только врач вручную — "
                           "я не могу их создавать или менять. Откройте «Ещё → Автослежение»."}

    # 1) открыть карту (проверяем РАНЬШЕ записи в карту: «открой карту Иванова»
    #    — это просьба показать, а не записать)
    if any(w in low for w in ("открой", "покажи", "найди", "открыть")):
        p = _find_patient(low, s)
        if p:
            return {"intent": "open_patient", "patient_id": p.id,
                    "message": f"Открываю карту: {p.short_name}"}

    # 2) правки/запись в карту пациента
    if "карт" in low:
        p = _find_patient(low, s)
        body = re.sub(r".*карт[уые]?\s*(пациента)?\s*[а-яё]*\s*[:\-]?", "", text, count=1, flags=re.I).strip()
        if p:
            n = Note(patient_id=p.id, text=body or text, source="voice")
            s.add(n); s.commit()
            return {"intent": "patient_note", "message": f"Заметка добавлена в карту: {p.short_name}", "patient_id": p.id}
        return _need_patient(text, "Заметку записать некуда.")

    # 1.4) пригласить на контроль: «пригласи Иванова на контроль через 6 месяцев».
    #      Частый урологический сценарий, тот же, что кнопками в карте.
    if any(w in low for w in ("пригласи", "на контроль", "контрольный осмотр",
                              "повторный приём", "повторный прием")):
        p = _find_patient(low, s)
        when = _resolve_datetime(low)
        if not when:
            m = re.search(r"через\s+(\d+)\s*мес", low)
            if m:                                   # «через 6 месяцев» — месяцы, не дни
                when = clock.now() + timedelta(days=30 * int(m.group(1)))
                when = when.replace(hour=10, minute=0, second=0, microsecond=0)
        if when and not _resolve_time(low):
            # час не назван — ставим рабочее утро, а не «сейчас плюс полгода»
            when = when.replace(hour=10, minute=0, second=0, microsecond=0)
        if p and when:
            a = Appointment(doctor_id=current_doctor_id(), patient_id=p.id, starts_at=when,
                            kind="repeat", reason="контроль")
            s.add(a); s.commit(); s.refresh(a)
            return {"intent": "appointment", "appointment_id": a.id, "patient_id": p.id,
                    "message": f"Контроль назначен: {p.short_name}, "
                               f"{when.strftime('%d.%m.%Y %H:%M')}"}
        if p and not when:
            return {"intent": "appointment", "patient_id": p.id,
                    "message": f"Понял, кого пригласить ({p.short_name}) — уточните срок."}
        if guess_surname(text):
            return _need_patient(text, "Пригласить на контроль некого.")

    # 1.5) назначение: «назначь Иванову тадалафил 5 мг раз в день месяц».
    #      Создаём как ПРЕДЛОЖЕНИЕ — действующим станет после подтверждения врача.
    if any(w in low for w in ("назнач", "выпиши", "пропиши", "рекомендую принимать")):
        p = _find_patient(low, s)
        if not p:
            return _need_patient(text, "Назначение сделать некому.")
        from .rx_dictation import parse as parse_rx
        from ..models import Prescription
        body = re.sub(r"^.*?(?:назнач\w*|выпиши|пропиши)\s*", "", text, count=1, flags=re.I)
        body = re.sub(rf"{re.escape(p.last_name)}\w*\s*", "", body, count=1, flags=re.I).strip()
        items = parse_rx(body or text)["items"]
        if not items:
            return {"intent": "prescription", "ok": False, "patient_id": p.id,
                    "message": "Не понял, что назначить — повторите с названием и дозой."}
        created = []
        for it in items:
            rx = Prescription(patient_id=p.id, encounter_id=active_encounter_id(s, p.id),
                              drug_name=it["drug_name"], dose=it["dose"],
                              category=it["category"], frequency=it["frequency"],
                              duration=it["duration"], route=it["route"],
                              source="ai_suggested", confirmed=False, status="planned")
            s.add(rx); created.append(it["drug_name"])
        s.commit()
        return {"intent": "prescription", "patient_id": p.id,
                "message": f"Предложено назначений для {p.short_name}: {len(created)} "
                           f"({', '.join(created)[:90]}). Подтвердите во вкладке «Назначения»."}

    # 1.6) показатель: «у Иванова ПСА 7,2» — заносим на подтверждение, как из документа
    if _looks_like_value(low):
        p = _find_patient(low, s)
        if p:
            from .parsing import parse_lab_text
            vals = parse_lab_text(text)["values"]
            if vals:
                from ..models import Observation
                for v in vals:
                    s.add(Observation(patient_id=p.id,
                                      encounter_id=active_encounter_id(s, p.id),
                                      parameter_code=v["parameter_code"],
                                      value_num=v.get("value_num"), unit=v.get("unit", ""),
                                      status="pending"))
                s.commit()
                names = ", ".join(v["parameter_code"] for v in vals)
                return {"intent": "observation", "patient_id": p.id,
                        "message": f"Записано на подтверждение ({p.short_name}): {names}"}

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
        # пациента нет, но фамилия в команде на приём явно звучала — предлагаем
        # завести карту, а не превращать запись пациента в задачу себе
        if not p and when and guess_surname(text):
            return _need_patient(text, "Записать на приём некого.")
        # иначе падаем в задачу

    # 2.5) правила не справились — спросим модель (если подключена).
    #      Модель НЕ выполняет ничего сама: она только подсказывает намерение,
    #      действие выполняет наш код по нашим же правилам. Без ключа
    #      parse_command вернёт None и поведение останется прежним.
    hint = _ai_hint(text, s)
    if hint is not None:
        return hint

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


# Слова, которые не могут быть фамилией (иначе предложим «создать карту Завтра»)
_NOT_A_NAME = {
    "запиши", "запишите", "записать", "назначь", "назначить", "выпиши", "пропиши",
    "напомни", "напоминать", "поставь", "добавь", "создай", "открой", "покажи",
    "найди", "карту", "карте", "карта", "пациента", "пациенту", "приём", "прием",
    "сегодня", "завтра", "послезавтра", "утром", "вечером", "днём", "ночью",
    "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
    "через", "каждый", "каждые", "срочно", "жалобы", "контроль", "анализ",
}


def guess_surname(text: str) -> str:
    """Достаём предполагаемую фамилию из фразы, чтобы предложить создать карту.

    Берём слово с заглавной буквы (кроме первого — там обычно глагол) либо
    слово после «пациента/карту». Ничего не создаём — только подсказка врачу.
    """
    words = re.findall(r"[А-ЯЁ][а-яё\-]{2,}|[а-яё\-]{3,}", text)
    after = re.search(r"(?:пациент\w*|карт\w*)\s+([А-ЯЁа-яё\-]{3,})", text, re.I)
    candidates = []
    if after:
        candidates.append(after.group(1))
    for i, w in enumerate(re.findall(r"\S+", text)):
        clean = re.sub(r"[^А-Яа-яЁёA-Za-z\-]", "", w)
        if len(clean) >= 4 and clean[:1].isupper() and i > 0:
            candidates.append(clean)
    for cand in candidates:
        base = cand.lower()
        if base in _NOT_A_NAME:
            continue
        # снимаем частые падежные окончания: Иванова/Иванову/Ивановым → Иванов
        # порядок важен: сначала длинные окончания. «ва»/«ву» не трогаем —
        # иначе «Сидорова» превращалось в «Сидоро» вместо «Сидоров».
        for end in ("ому", "ему", "ого", "его", "ым", "ом", "ой", "ей", "у", "а", "е"):
            if base.endswith(end) and len(base) - len(end) >= 4:
                base = base[: -len(end)]
                break
        return base.capitalize()
    return ""


def _need_patient(text: str, what: str) -> dict:
    """Единый ответ, когда пациент не найден: предлагаем создать карту.

    Сами НЕ создаём: фамилия на слух и склонения ненадёжны, а дубль карты
    разрывает историю пациента. Врач подтверждает и дозаполняет.
    """
    surname = guess_surname(text)
    msg = (f"Не нашёл пациента{' «' + surname + '»' if surname else ''}. "
           f"{what} Создать карту?" if surname
           else f"Не нашёл пациента. {what} Уточните фамилию.")
    return {"intent": "patient_missing", "ok": False, "patient_id": None,
            "suggest_create": bool(surname), "surname": surname, "message": msg}


def _resolve_datetime(low: str):
    """Дата-время из фразы врача (см. services/rudate)."""
    from .rudate import parse_datetime
    return parse_datetime(low)


def _resolve_time(low: str):
    from .rudate import parse_time
    hm = parse_time(low)
    return f"{hm[0]:02d}:{hm[1]:02d}" if hm else None


def _override_due(low: str):
    """Для задач: «сегодня вечером» и т.п. дают дату+время."""
    dt = _resolve_datetime(low)
    return dt


def _looks_like_value(low: str) -> bool:
    """Похоже ли на продиктованный показатель: есть название и число."""
    from ..reference_data import synonyms_index
    if not re.search(r"\d", low):
        return False
    for terms in synonyms_index().values():
        for t in terms:
            if len(t) >= 3 and re.search(r"(?<![а-яёa-z0-9])" + re.escape(t) +
                                         r"(?![а-яёa-z0-9])", low):
                return True
    return False


def _ai_hint(text: str, s: Session):
    """Уточнение намерения моделью. Возвращает готовый ответ или None (идём дальше).

    Принципы: модель только классифицирует, действие делает наш код; при низкой
    уверенности и при «unknown» ничего не создаём молча, а честно переспрашиваем.
    """
    from . import ai
    low = text.lower()
    res = ai.parse_command(text)
    if not res:
        return None

    intent, conf = res["intent"], res["confidence"]
    if conf < 0.5:
        return None                      # не уверена — пусть работают правила

    if intent == "appointment":
        p = _find_patient((res["patient_hint"] or "").lower() or low, s)
        # время, посчитанное моделью, приоритетнее: она понимает «в 3 часа дня»
        when = res.get("datetime") or _resolve_datetime(low)
        if p and when:
            a = Appointment(doctor_id=current_doctor_id(), patient_id=p.id, starts_at=when,
                            kind="repeat", reason="запись голосом")
            s.add(a); s.commit(); s.refresh(a)
            return {"intent": "appointment",
                    "message": f"Записан приём: {p.short_name}, {when.strftime('%d.%m %H:%M')}",
                    "appointment_id": a.id}
        if p and not when:
            return {"intent": "appointment",
                    "message": f"Кого записать понял ({p.short_name}), а когда — уточните дату и время"}
        return {"intent": "appointment", "message": "Похоже на запись на приём — уточните пациента и время"}

    if intent == "patient_note":
        p = _find_patient((res["patient_hint"] or "").lower() or low, s)
        if p:
            body = res["title"] or text
            n = Note(patient_id=p.id, text=body, source="voice")
            s.add(n); s.commit()
            return {"intent": "patient_note",
                    "message": f"Заметка добавлена в карту: {p.short_name}", "patient_id": p.id}
        return _need_patient(text, "Понял, что это запись в карту.")

    if intent == "task":
        when = res.get("datetime")
        if not when:
            return None                      # срока модель не дала — пусть решают правила
        from ..models import Reminder
        from .nlp import parse_reminder
        title = res["title"] or text
        urgent = "сроч" in (res.get("priority") or "").lower()
        # повтор берём из самой фразы: модель может его не вернуть, а врач сказал
        parsed = parse_reminder(text)
        r = Reminder(doctor_id=current_doctor_id(), title=title, due_at=when,
                     kind="task", priority=1 if urgent else 4, source="voice",
                     repeat_days=parsed.get("repeat_days"),
                     project=parsed.get("project") or "Входящие")
        s.add(r); s.commit(); s.refresh(r)
        from .alerts import set_alerts
        set_alerts(s, r.doctor_id, "reminder", r.id, r.due_at, kind=r.kind)
        rep = f" · повтор каждые {r.repeat_days} дн." if r.repeat_days else ""
        return {"intent": "task", "reminder_id": r.id,
                "message": f"Задача создана: {title} ({when.strftime('%d.%m %H:%M')})"
                           + (" · срочная" if urgent else "") + rep}

    if intent == "unknown":
        # ничего не выдумываем и не создаём «мусорную» задачу
        return {"intent": "unknown", "ok": False,
                "message": "Не понял команду. Я умею: записать на приём, добавить заметку "
                           "в карту пациента и поставить задачу. Диагнозы, назначения и "
                           "триггеры — только вручную."}

    return None                          # intent == "task" → обычный путь ниже
