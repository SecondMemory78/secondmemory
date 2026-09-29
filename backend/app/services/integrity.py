"""Детерминированный контроль целостности карты пациента (D-правила из ТЗ, без ИИ).

Только СИГНАЛИЗИРУЕТ (read-only), ничего не меняет и не удаляет. Уровни реакции:
  D — ошибка структуры/дат (показать, что проверить);
  Q — клиническое уточнение по справочнику (вопрос, не запрет);
  I — недостаточно сведений (уточнить поле).
ИИ-проверки свободного текста (D01/D07, Q03) — отдельно, при подключении ключей.

Проверки, не требующие ИИ:
  D02 — некорректные/невозможные даты: событие раньше рождения; выписка раньше
        поступления; поступление/дата события в будущем.
  D03 — устройство закрыто раньше установки, либо активно и закрыто одновременно.
  D05 — значение показателя вне допустимого (отрицательное там, где невозможно).
  Q02 — два актуальных назначения с одним МНН (по справочнику normalize_drug) —
        сигнал проверить дозу/форму/намеренность; препараты НЕ отменяем.
  Q01 — активное назначение конфликтует с подтверждённой аллергией пациента
        (переиспользует справочную check_conflict: прямое/групповое/перекрёстное).
  I   — значение есть, а единица измерения не указана.
"""
from datetime import date
from sqlmodel import Session, select
from ..models import Patient, Observation, Encounter, Prescription
from .. import clock

# Параметры, для которых отрицательное значение бессмысленно (лабораторные/измерения).
_NONNEGATIVE_HINT = True   # почти все урологические показатели неотрицательны


def check_patient(s: Session, pid: int) -> list[dict]:
    p = s.get(Patient, pid)
    if not p:
        return []
    findings = []
    today = clock.today()

    obs = s.exec(select(Observation).where(Observation.patient_id == pid)).all()
    for o in obs:
        # D02: дата результата раньше даты рождения или в будущем
        if o.effective_date and p.birth_date and o.effective_date < p.birth_date:
            findings.append(_f("D02", "D", "Дата показателя раньше даты рождения пациента.",
                               {"parameter": o.parameter_code, "date": o.effective_date.isoformat()}))
        if o.effective_date and o.effective_date > today:
            findings.append(_f("D02", "D", "Дата показателя в будущем — возможно, опечатка.",
                               {"parameter": o.parameter_code, "date": o.effective_date.isoformat()}))
        # D05: отрицательное числовое значение показателя
        if o.value_num is not None and o.value_num < 0:
            findings.append(_f("D05", "D", "Отрицательное значение показателя — проверьте ввод.",
                               {"parameter": o.parameter_code, "value": o.value_num}))
        # I: значение есть, единица не указана
        if o.value_num is not None and not (o.unit or "").strip():
            findings.append(_f("I", "I", "У значения не указана единица измерения.",
                               {"parameter": o.parameter_code, "value": o.value_num}))

    enc = s.exec(select(Encounter).where(Encounter.patient_id == pid)).all()
    for e in enc:
        # D02: фактическая выписка раньше фактического поступления
        if e.actual_admission_at and e.actual_discharge_at and e.actual_discharge_at < e.actual_admission_at:
            findings.append(_f("D02", "D", "Выписка раньше поступления — проверьте даты эпизода.",
                               {"encounter_id": e.id}))
        # D02: фактическое поступление в будущем (для плановой даты есть отдельное поле)
        if e.actual_admission_at and e.actual_admission_at.date() > today:
            findings.append(_f("D02", "D", "Фактическое поступление датировано будущим — возможно, это плановая дата.",
                               {"encounter_id": e.id}))
        # D02: событие эпизода раньше рождения
        if e.actual_admission_at and p.birth_date and e.actual_admission_at.date() < p.birth_date:
            findings.append(_f("D02", "D", "Дата поступления раньше даты рождения пациента.",
                               {"encounter_id": e.id}))

    # D03: устройство удалено раньше установки, либо одновременно активно и закрыто.
    from ..models import Device
    devs = s.exec(select(Device).where(Device.patient_id == pid)).all()
    for d in devs:
        if d.installed_at and d.closed_at and d.closed_at < d.installed_at:
            findings.append(_f("D03", "D", "Устройство закрыто раньше даты установки — проверьте device_id и даты.",
                               {"device_id": d.id, "kind": d.kind}))
        if d.active and d.closed_at:
            findings.append(_f("D03", "D", "Устройство отмечено активным, но у него есть дата закрытия.",
                               {"device_id": d.id, "kind": d.kind}))

    # Q02: два АКТУАЛЬНЫХ назначения с одним действующим веществом (МНН); плюс сигнал,
    # если один МНН есть одновременно активным и отменённым (намеренность — вопрос врачу).
    # Только сигнал: разные дозы/формы/интервалы и комбинирование возможны; не отменяем.
    from ..reference_data import normalize_drug
    rx = s.exec(select(Prescription).where(Prescription.patient_id == pid)).all()
    active_inn = {}
    inn_states = {}
    for r in rx:
        inn = normalize_drug(r.drug_name or "")
        if not inn:
            continue
        inn_states.setdefault(inn, set()).add(r.status)
        if r.status == "active":
            if inn in active_inn:
                findings.append(_f("Q02", "Q", "Два актуальных назначения с одним действующим веществом — проверьте дозу, форму и намеренность комбинации.",
                                   {"inn": inn, "drugs": [active_inn[inn], r.drug_name]}))
            else:
                active_inn[inn] = r.drug_name
    for inn, states in inn_states.items():
        if "active" in states and "cancelled" in states:
            findings.append(_f("Q02", "Q", "Действующее вещество отмечено и активным, и отменённым — уточните намеренность.",
                               {"inn": inn}))

    # Q01: активное назначение конфликтует с подтверждённой аллергией пациента.
    # Переиспользуем справочную проверку check_conflict (прямое/групповое/перекрёстное
    # совпадение по справочнику). Только сигнал-вопрос; замену не подбираем, не отменяем.
    from ..models import SafetyItem
    from .allergy import check_conflict
    allergies = s.exec(select(SafetyItem).where(
        SafetyItem.patient_id == pid, SafetyItem.kind == "allergy")).all()
    if any(a.state == "present" and a.detail for a in allergies):
        for r in rx:
            if r.status != "active":
                continue
            conflict = check_conflict(r.drug_name, allergies)
            if conflict:
                findings.append(_f("Q01", "Q",
                                   f"Назначение «{r.drug_name}» может конфликтовать с аллергией: {conflict['message']}. Проверьте вещество, реакцию и актуальность.",
                                   {"drug": r.drug_name, "group": conflict.get("group", ""),
                                    "cross_rule": conflict.get("cross_rule", "")}))

    return findings


def _f(rule: str, level: str, message: str, refs: dict) -> dict:
    return {"rule": rule, "level": level, "message": message, "refs": refs}
