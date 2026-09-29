"""Эпизоды (encounters). За простым интерфейсом — логика:
- active_encounter_id() — совместимость: единственный открытый эпизод;
- resolve_encounter() — «к какому эпизоду отнести запись», если открытых несколько;
- day_of_stay() — честный подсчёт дня пребывания (None, если дата поступления не указана).
"""
from datetime import datetime
from sqlmodel import Session, select
from ..models import Encounter
from .. import clock


def open_encounters(s: Session, patient_id: int):
    return s.exec(select(Encounter).where(Encounter.patient_id == patient_id,
                                          Encounter.status == "open")).all()


def active_encounter_id(s: Session, patient_id: int):
    """Единственный открытый эпизод (совместимость со старым кодом).
    Если открытых несколько — возвращаем None (неоднозначно, нужен явный выбор)."""
    rows = open_encounters(s, patient_id)
    return rows[0].id if len(rows) == 1 else None


def resolve_encounter(s: Session, patient_id: int, encounter_id=None):
    """Куда привязать запись. Возвращает (encounter_id | None, ambiguous: bool).
    - явный encounter_id (валидный, открытый) → он;
    - ровно один открытый → он;
    - несколько открытых и явного нет → (None, ambiguous=True) — надо спросить врача;
    - ни одного открытого → (None, False)."""
    if encounter_id is not None:
        e = s.get(Encounter, encounter_id)
        if e and e.patient_id == patient_id and e.status == "open":
            return e.id, False
    rows = open_encounters(s, patient_id)
    if len(rows) == 1:
        return rows[0].id, False
    if len(rows) >= 2:
        return None, True
    return None, False


def day_of_stay(e: Encounter):
    """Номер дня пребывания в стационаре (1 = день поступления). None, если это не
    госпитализация или дата поступления не указана — числа не выдумываем."""
    if e.type != "hospitalization" or not e.actual_admission_at:
        return None
    end = e.actual_discharge_at or clock.now()
    return (end.date() - e.actual_admission_at.date()).days + 1
