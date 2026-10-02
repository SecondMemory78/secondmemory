"""Каталог действий: единственное место, где решается, что ассистенту можно.

Раньше каждое умение ассистента было веткой в коде, и правила приходилось
повторять в каждой. Теперь правило живёт в описании действия, а проверка — в
единственном исполнителе. Эти тесты следят, чтобы его нельзя было обойти.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Patient, Prescription, Observation
from app.services import actions as acts
from app.services import assistant_actions  # noqa: F401 — регистрирует умения

seed.run()
c = TestClient(app)


def _patient():
    with Session(engine) as s:
        return s.exec(select(Patient)).first()


# ── запреты ─────────────────────────────────────────────────────────────────

def test_ассистенту_запрещены_три_вещи():
    forbidden = {a.name for a in acts.all_actions() if a.level == acts.DOCTOR_ONLY}
    assert {"trigger.manage", "patient.create", "medical.delete"} <= forbidden


def test_запрещённое_не_выполняется_ассистентом():
    for name in ("trigger.manage", "patient.create", "medical.delete"):
        with pytest.raises(acts.ActionDenied):
            acts.run(name, by="assistant")


def test_отказ_объясняет_причину_врачу():
    with pytest.raises(acts.ActionDenied) as e:
        acts.run("trigger.manage", by="assistant")
    assert "врач" in str(e.value).lower()


def test_запрещённых_нет_в_списке_для_ассистента():
    names = {a.name for a in acts.for_assistant()}
    assert "trigger.manage" not in names
    assert "patient.create" not in names


def test_несуществующее_действие_отклоняется():
    with pytest.raises(acts.ActionUnknown):
        acts.run("ничего.такого", by="assistant")


# ── запись только с подтверждением ──────────────────────────────────────────

def test_назначение_от_ассистента_остаётся_предложением():
    p = _patient()
    with Session(engine) as s:
        acts.run("prescription.suggest", by="assistant", s=s, patient=p,
                 items=[{"drug_name": "Тамсулозин", "dose": "0,4 мг", "category": "drug",
                         "frequency": "на ночь", "duration": "1 месяц", "route": ""}])
        rx = s.exec(select(Prescription).where(
            Prescription.patient_id == p.id)).all()[-1]
        assert rx.confirmed is False
        assert rx.status == "planned"
        assert rx.source == "ai_suggested"


def test_показатель_от_ассистента_ждёт_проверки():
    p = _patient()
    with Session(engine) as s:
        acts.run("observation.add", by="assistant", s=s, patient=p,
                 values=[{"parameter_code": "psa_total", "value_num": 7.2, "unit": "нг/мл"}])
        o = s.exec(select(Observation).where(Observation.patient_id == p.id)).all()[-1]
        assert o.status == "pending"
        assert o.machine_extracted is True
        assert o.confirmed_by is None


# ── целостность каталога ────────────────────────────────────────────────────

def test_у_каждого_действия_есть_уровень_и_название():
    for a in acts.all_actions():
        assert a.level in acts.LEVELS
        assert a.title.strip(), f"{a.name}: нет человеческого названия"


def test_уровень_проверяется_при_объявлении():
    with pytest.raises(ValueError):
        acts.Action(name="плохое", level="что-то своё", title="Проверка")


def test_действия_не_дублируются():
    names = [a.name for a in acts.all_actions()]
    assert len(names) == len(set(names))
