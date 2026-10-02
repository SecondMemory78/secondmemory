"""Изоляция тестов.

База у всех тестов общая: движок создаётся один раз при импорте приложения.
Это дважды кусало за сессию — соседний файл менял общего пациента, и тест
падал ТОЛЬКО в полном прогоне, а поодиночке проходил. Искать такую поломку
тяжело.

Правило: читаешь — можно общего пациента, МЕНЯЕШЬ — заводи своего.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Patient, PatientDiagnosis

seed.run()
c = TestClient(app)


def test_адрес_базы_задан_централизованно():
    """Иначе побеждает тот файл, который импортировался первым."""
    assert os.environ["DATABASE_URL"].startswith("sqlite:///")


def test_свой_пациент_не_виден_другим_после_теста(own_patient):
    p = own_patient(last_name="Изоляциев")
    with Session(engine) as s:
        assert s.get(Patient, p.id) is not None
    # после теста фикстура уберёт его — проверяется следующим тестом
    globals()["_leaked_id"] = p.id


def test_за_собой_убрано():
    """Список пациентов не должен разрастаться от чужих тестов."""
    leaked = globals().get("_leaked_id")
    if leaked is None:
        return
    with Session(engine) as s:
        assert s.get(Patient, leaked) is None, "тестовый пациент остался в базе"


def test_правка_своего_не_трогает_общего(own_patient):
    """Ровно тот случай, на котором мы обожглись: смена основного диагноза."""
    with Session(engine) as s:
        shared = s.exec(select(Patient).where(Patient.last_name != "Изоляциев")).first()
        before = shared.diagnosis_code

    mine = own_patient(last_name="Диагнозов", with_consent=True)
    r = c.post(f"/api/patients/{mine.id}/diagnoses",
               json={"code": "N20.0", "wording": "Камень почки"})
    assert r.status_code == 200, r.text

    with Session(engine) as s:
        assert s.get(Patient, shared.id).diagnosis_code == before
        mine_dx = s.exec(select(PatientDiagnosis).where(
            PatientDiagnosis.patient_id == mine.id)).all()
        assert len(mine_dx) == 1
