"""Детерминированный контроль целостности карты пациента (D-правила из ТЗ, без ИИ).

Только СИГНАЛИЗИРУЕТ (read-only), ничего не меняет и не удаляет. Уровни реакции:
  D — ошибка структуры/дат (показать, что проверить);
  I — недостаточно сведений (уточнить поле).
Клинические уточнения (Q) и ИИ-проверки (D01/D07) — отдельно, при подключении ключей.

Проверки, не требующие ИИ:
  D02 — некорректные/невозможные даты: событие раньше рождения; выписка раньше
        поступления; поступление/дата события в будущем.
  D05 — значение показателя вне допустимого (отрицательное там, где невозможно).
  I   — значение есть, а единица измерения не указана.
"""
from datetime import date
from sqlmodel import Session, select
from ..models import Patient, Observation, Encounter
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

    return findings


def _f(rule: str, level: str, message: str, refs: dict) -> dict:
    return {"rule": rule, "level": level, "message": message, "refs": refs}
