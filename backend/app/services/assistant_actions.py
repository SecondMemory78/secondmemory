"""Умения ассистента как отдельные действия каталога.

Раньше каждое из них было веткой внутри одной длинной функции разбора команд.
Из-за этого правила («показатель заносим на подтверждение», «назначение —
только предложение») приходилось помнить и повторять в каждой ветке, а
ассистент не мог узнать, что он вообще умеет.

Теперь каждое умение — функция с именем, и оно зарегистрировано в каталоге
(services/actions). Разбор команды только выбирает действие и собирает для
него данные; выполняет всё единый исполнитель, он же проверяет доступ.
"""
from datetime import datetime, timedelta

from sqlmodel import Session

from .. import clock
from ..deps import current_doctor_id
from ..models import Appointment, Note, Reminder
from .actions import Action, CONFIRM, READ, register
from .visits import active_encounter_id


def ask_question(*, by: str = "doctor", s: Session, text: str) -> dict:
    """Вопрос к картотеке. Только чтение — ничего не меняет."""
    from .query import ask
    return ask(s, text)


def open_patient(*, by: str = "doctor", s: Session, patient) -> dict:
    """Просто показать карту — ничего не меняет."""
    return {"intent": "open_patient", "patient_id": patient.id,
            "message": f"Открываю карту: {patient.short_name}"}


def add_note(*, by: str = "doctor", s: Session, patient, text: str) -> dict:
    n = Note(patient_id=patient.id, text=text, source="voice")
    s.add(n); s.commit()
    return {"intent": "patient_note", "patient_id": patient.id,
            "message": f"Заметка добавлена в карту: {patient.short_name}"}


def create_appointment(*, by: str = "doctor", s: Session, patient, when: datetime,
                       reason: str = "запись голосом", kind: str = "repeat") -> dict:
    a = Appointment(doctor_id=current_doctor_id(), patient_id=patient.id,
                    starts_at=when, kind=kind, reason=reason)
    s.add(a); s.commit(); s.refresh(a)
    label = "Контроль назначен" if reason == "контроль" else "Записан приём"
    fmt = "%d.%m.%Y %H:%M" if reason == "контроль" else "%d.%m %H:%M"
    return {"intent": "appointment", "appointment_id": a.id, "patient_id": patient.id,
            "message": f"{label}: {patient.short_name}, {when.strftime(fmt)}"}


def suggest_prescriptions(*, by: str = "doctor", s: Session, patient, items: list) -> dict:
    """Назначения создаются ПРЕДЛОЖЕНИЕМ: действующими станут после врача."""
    from ..models import Prescription
    created, rows = [], []
    for it in items:
        rx = Prescription(patient_id=patient.id,
                          encounter_id=active_encounter_id(s, patient.id),
                          drug_name=it["drug_name"], dose=it["dose"],
                          category=it["category"], frequency=it["frequency"],
                          duration=it["duration"], route=it["route"],
                          source="ai_suggested", confirmed=False, status="planned")
        s.add(rx); rows.append(rx); created.append(it["drug_name"])
    s.commit()
    # Идентификаторы нужны журналу: без них нечего связать с подтверждением
    # врача, и в логе останется только «предложено», без «чем закончилось».
    ids = [r.id for r in rows]
    return {"intent": "prescription", "patient_id": patient.id,
            "prescription_ids": ids,
            "message": f"Предложено назначений для {patient.short_name}: {len(created)} "
                       f"({', '.join(created)[:90]}). Подтвердите во вкладке «Назначения»."}


# Сведения СО СЛОВ пациента — не измерение. Врач говорит «пациент сказал, что
# ПСА был семь» — это анамнез, а не лабораторный результат, и показывать его
# рядом с настоящими значениями нельзя: через месяц никто не вспомнит разницу.
PATIENT_WORDS = ("со слов", "по словам", "пациент говорит", "пациент сказал",
                 "жалуется", "утверждает", "рассказал", "рассказывает")


def said_by_patient(text: str) -> bool:
    return any(w in (text or "").lower() for w in PATIENT_WORDS)


def add_observations(*, by: str = "doctor", s: Session, patient, values: list,
                     said_text: str = "") -> dict:
    """Показатели заносятся как ожидающие проверки — ровно как из документа.

    Если врач сказал «со слов пациента», значение помечается источником
    patient_words: оно останется в карте, но не будет выглядеть измерением.
    """
    from ..models import Observation
    from_patient = said_by_patient(said_text)
    rows = []
    for v in values:
        o = Observation(patient_id=patient.id,
                        encounter_id=active_encounter_id(s, patient.id),
                        parameter_code=v["parameter_code"],
                        value_num=v.get("value_num"), unit=v.get("unit", ""),
                        status="pending",
                        provenance="patient_words" if from_patient else "ai_extracted",
                        machine_extracted=True)
        s.add(o); rows.append(o)
    s.commit()
    names = ", ".join(v["parameter_code"] for v in values)
    tail = " (со слов пациента)" if from_patient else ""
    return {"intent": "observation", "patient_id": patient.id,
            "observation_ids": [o.id for o in rows],
            "message": f"Записано на подтверждение ({patient.short_name}): {names}{tail}"}


def create_task(*, by: str = "doctor", s: Session, parsed: dict, due) -> dict:
    r = Reminder(doctor_id=current_doctor_id(), title=parsed["title"], due_at=due,
                 kind=parsed["kind"], priority=parsed["priority"],
                 repeat_days=parsed["repeat_days"], labels=parsed["labels"],
                 project=parsed["project"], source="voice")
    s.add(r); s.commit(); s.refresh(r)
    when_txt = due.strftime("%d.%m %H:%M") if due else "без срока"
    return {"intent": "task", "reminder_id": r.id,
            "message": f"Задача создана: {r.title} ({when_txt})"}


def add_device(*, by: str = "doctor", s: Session, patient, kind: str, side: str = "",
               due_at=None, note: str = "") -> dict:
    """Поставить устройство. Сторона обязательна по смыслу: перепутать бок —
    самая дорогая ошибка в этом месте, поэтому если её не назвали, просим."""
    from ..models import Device
    from ..routers.devices import SIDES, SIDE_LABELS, KINDS
    if kind not in KINDS:
        return {"intent": "device", "ok": False,
                "message": "Не понял, какое устройство: катетер, стент или нефростома?"}
    if side not in SIDES:
        side = ""
    if kind in ("stent", "nephrostomy") and not side:
        return {"intent": "device", "ok": False, "patient_id": patient.id,
                "message": "С какой стороны — слева или справа?"}
    d = Device(doctor_id=current_doctor_id(), patient_id=patient.id, kind=kind,
               side=side, active=True, installed_at=clock.today(), due_at=due_at, note=note)
    s.add(d); s.commit(); s.refresh(d)
    name = {"stent": "стент", "nephrostomy": "нефростома", "catheter": "катетер"}[kind]
    if side:
        name += " " + SIDE_LABELS[side]
    return {"intent": "device", "patient_id": patient.id, "device_id": d.id,
            "message": f"Записано: {name} — {patient.short_name}"
                       + ("" if due_at else ". Срок замены не назначен — укажите в карте.")}


def close_device(*, by: str = "doctor", s: Session, patient, kind: str = "",
                 side: str = "") -> dict:
    """Снять устройство. Если подходящих несколько — не угадываем, а спрашиваем:
    закрыть не то устройство хуже, чем переспросить."""
    from ..models import Device
    from sqlmodel import select as _select
    devs = s.exec(_select(Device).where(Device.patient_id == patient.id,
                                        Device.active == True)).all()      # noqa: E712
    if kind:
        devs = [d for d in devs if d.kind == kind]
    if side:
        devs = [d for d in devs if d.side == side]
    if not devs:
        return {"intent": "device", "ok": False, "patient_id": patient.id,
                "message": f"У {patient.short_name} нет подходящего активного устройства."}
    if len(devs) > 1:
        return {"intent": "device", "ok": False, "patient_id": patient.id,
                "message": "Подходит несколько устройств — уточните сторону или "
                           "снимите в карте, во вкладке «Устройства»."}
    d = devs[0]
    d.active = False
    d.state = "removed"
    d.closed_at = clock.today()
    d.closed_action = "removed"
    s.add(d); s.commit()
    return {"intent": "device", "patient_id": patient.id, "device_id": d.id,
            "message": f"Устройство снято: {patient.short_name}"}


def add_diagnosis(*, by: str = "doctor", s: Session, patient, query: str) -> dict:
    """Поставить диагноз. Код НЕ выдумываем: берём только из справочника МКБ.

    Если по сказанному нашлось несколько подходящих — не выбираем за врача,
    а показываем варианты: неверный код в карте выглядит как факт и уедет
    в документы.
    """
    from ..models import PatientDiagnosis
    from ..reference_data import find_icd
    q = (query or "").strip()
    found = find_icd(q, limit=5)
    if not found and "." in q:
        # В справочнике коды без подрубрик: «N40», а не «N40.0». Врач называет
        # с подрубрикой — ищем по основному коду, иначе честный диагноз
        # отвергался бы как несуществующий.
        q = q.split(".")[0]
        found = find_icd(q, limit=5)
    if not found:
        return {"intent": "diagnosis", "ok": False, "patient_id": patient.id,
                "message": f"Не нашёл в справочнике МКБ: «{query}». "
                           f"Поставьте диагноз в карте."}
    if len(found) > 1 and not any(f["code"].lower() == q.lower() for f in found):
        variants = ", ".join(f"{f['code']} {f['title']}" for f in found[:3])
        return {"intent": "diagnosis", "ok": False, "patient_id": patient.id,
                "message": f"Подходит несколько: {variants}. Уточните код."}
    item = next((f for f in found if f["code"].lower() == q.lower()), found[0])

    # Основным диагноз от ассистента НЕ становится: основной определяет шапку
    # карты и попадает в документы — это решение врача, а не разбор фразы.
    # Предложение, а не запись: диагноз — клиническое суждение, и ошибка в нём
    # весит не меньше, чем в назначении.
    d = PatientDiagnosis(patient_id=patient.id, code=item["code"], title=item["title"],
                         encounter_id=active_encounter_id(s, patient.id),
                         is_primary=False, confirmed=False, source="ai_suggested")
    s.add(d); s.commit(); s.refresh(d)
    return {"intent": "diagnosis", "patient_id": patient.id, "diagnosis_id": d.id,
            "message": f"Предложен диагноз: {item['code']} {item['title']} — "
                       f"{patient.short_name}. Подтвердите в карте."}


def start_encounter(*, by: str = "doctor", s: Session, patient, reason: str = "приём") -> dict:
    """Начать приём. Если визит уже открыт — не плодим второй, а говорим об этом."""
    from ..services.visits import active_encounter_id as _active
    from ..models import Encounter
    if _active(s, patient.id):
        return {"intent": "encounter", "ok": False, "patient_id": patient.id,
                "message": f"Приём у {patient.short_name} уже открыт."}
    e = Encounter(doctor_id=current_doctor_id(), patient_id=patient.id, reason=reason)
    s.add(e); s.commit(); s.refresh(e)
    return {"intent": "encounter", "patient_id": patient.id, "encounter_id": e.id,
            "message": f"Приём начат: {patient.short_name}"}


# ── Регистрация в каталоге ──────────────────────────────────────────────────
register(Action(name="patient.search", level=READ, title="Найти пациентов по условиям",
                run=ask_question, args=("text",)))
register(Action(name="patient.open", level=READ, title="Открыть карту пациента",
                run=open_patient, args=("patient",)))
register(Action(name="patient.note", level=CONFIRM, title="Заметка в карту",
                run=add_note, args=("patient", "text")))
register(Action(name="appointment.create", level=CONFIRM, title="Запись на приём",
                run=create_appointment, args=("patient", "when")))
register(Action(name="prescription.suggest", level=CONFIRM, title="Предложить назначение",
                run=suggest_prescriptions, args=("patient", "items")))
register(Action(name="observation.add", level=CONFIRM, title="Внести показатель",
                run=add_observations, args=("patient", "values")))
register(Action(name="task.create", level=CONFIRM, title="Создать задачу",
                run=create_task, args=("parsed",)))
register(Action(name="device.add", level=CONFIRM, title="Поставить устройство",
                run=add_device, args=("patient", "kind")))
register(Action(name="device.close", level=CONFIRM, title="Снять устройство",
                run=close_device, args=("patient",)))
register(Action(name="diagnosis.add", level=CONFIRM, title="Поставить диагноз",
                run=add_diagnosis, args=("patient", "query")))
register(Action(name="encounter.start", level=CONFIRM, title="Начать приём",
                run=start_encounter, args=("patient",)))
