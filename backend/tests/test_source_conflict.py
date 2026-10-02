"""Конфликт источников: документ говорит одно, пациент другое.

Отличается от обычного расхождения тем, что здесь понятно, какой источник
надёжнее. И всё равно выбирать за врача нельзя: пациент может помнить верно,
а документ оказаться чужим или устаревшим. Наше дело — показать оба значения
и назвать источники.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date
from sqlmodel import Session
from app.main import app  # noqa: F401 — поднимает приложение и движок
from app import seed
from app.db import engine
from app.deps import set_current_doctor_id
from app.models import Observation
from app.services.integrity import find_conflicts, conflicting_observations

seed.run()
set_current_doctor_id(1)
DAY = date(2026, 5, 20)


def _add(pid, value, provenance, status="confirmed"):
    with Session(engine) as s:
        s.add(Observation(patient_id=pid, parameter_code="psa_total",
                          value_num=value, unit="нг/мл", effective_date=DAY,
                          status=status, provenance=provenance))
        s.commit()


def _c04(pid):
    with Session(engine) as s:
        return [c for c in find_conflicts(s, pid) if c["rule"] == "C04"]


def test_расхождение_источников_замечено(own_patient):
    p = own_patient(last_name="Конфликтов")
    _add(p.id, 4.8, "document")
    _add(p.id, 7.2, "patient_words")
    items = _c04(p.id)
    assert items, "конфликт источников не найден"
    text = items[0]["message"]
    assert "в документе" in text and "со слов пациента" in text


def test_мы_не_выбираем_за_врача(own_patient):
    p = own_patient(last_name="Решаев")
    _add(p.id, 4.8, "document")
    _add(p.id, 7.2, "patient_words")
    assert "автоматически мы не решаем" in _c04(p.id)[0]["message"]
    # оба значения остаются в карте
    with Session(engine) as s:
        from sqlmodel import select
        vals = {o.value_num for o in s.exec(select(Observation).where(
            Observation.patient_id == p.id)).all()}
    assert {4.8, 7.2} <= vals


def test_совпавшие_значения_не_конфликт(own_patient):
    """Пациент вспомнил верно — ругаться не на что."""
    p = own_patient(last_name="Совпадаев")
    _add(p.id, 4.8, "document")
    _add(p.id, 4.8, "patient_words")
    assert _c04(p.id) == []


def test_только_документ_не_конфликт(own_patient):
    p = own_patient(last_name="Документов")
    _add(p.id, 4.8, "document")
    assert _c04(p.id) == []


def test_конфликтующий_показатель_не_идёт_в_памятку(own_patient):
    """То же правило, что и для обычных расхождений."""
    p = own_patient(last_name="Памяткин")
    _add(p.id, 4.8, "document")
    _add(p.id, 7.2, "patient_words")
    with Session(engine) as s:
        assert "psa_total" in conflicting_observations(s, p.id)
