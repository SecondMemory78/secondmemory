"""Конфликты данных.

ТЗ: противоречащие значения не перезаписываются молча — они сохраняются
параллельно, показываются врачу и НЕ разрешаются автоматически. Пока конфликт
не снят, такие данные не попадают в документы для пациента.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed
from app.db import engine
from app.models import Observation, Device
from app.services.integrity import find_conflicts, conflicting_observations
from app.services.pdf_export import handout_sections

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def _obs(pid, code, value, day, status="confirmed"):
    with Session(engine) as s:
        s.add(Observation(patient_id=pid, parameter_code=code, value_num=value,
                          unit="нг/мл", effective_date=day, status=status))
        s.commit()


def test_два_значения_на_одну_дату_это_конфликт():
    pid = _pid()
    _obs(pid, "psa_conf", 4.8, date(2026, 9, 1))
    _obs(pid, "psa_conf", 7.2, date(2026, 9, 1))
    with Session(engine) as s:
        found = [f for f in find_conflicts(s, pid) if f["rule"] == "C01"]
        assert found, "конфликт не обнаружен"
        assert "psa_conf" in found[0]["message"]
        assert "psa_conf" in conflicting_observations(s, pid)


def test_разные_даты_конфликтом_не_считаются():
    """Это обычная динамика, а не противоречие."""
    pid = _pid()
    _obs(pid, "psa_dyn", 3.1, date(2026, 1, 10))
    _obs(pid, "psa_dyn", 4.8, date(2026, 9, 1))
    with Session(engine) as s:
        assert "psa_dyn" not in conflicting_observations(s, pid)


def test_одинаковые_значения_не_конфликт():
    pid = _pid()
    _obs(pid, "psa_same", 4.8, date(2026, 8, 1))
    _obs(pid, "psa_same", 4.8, date(2026, 8, 1))
    with Session(engine) as s:
        assert "psa_same" not in conflicting_observations(s, pid)


def test_конфликт_не_решается_автоматически():
    """Ни одно значение не помечается верным и ничего не удаляется."""
    pid = _pid()
    _obs(pid, "psa_keep", 1.0, date(2026, 7, 1))
    _obs(pid, "psa_keep", 2.0, date(2026, 7, 1))
    with Session(engine) as s:
        rows = [o for o in s.exec(
            __import__("sqlmodel").select(Observation).where(
                Observation.patient_id == pid)).all() if o.parameter_code == "psa_keep"]
        assert len(rows) == 2
        assert {o.status for o in rows} == {"confirmed"}


def test_конфликтующий_показатель_не_печатается():
    s = {x["key"]: x for x in handout_sections({
        "observations": [
            {"parameter_code": "psa", "label": "ПСА", "value_num": 3.1, "unit": "нг/мл",
             "effective_date": "2026-01-10", "status": "confirmed"},
            {"parameter_code": "psa", "label": "ПСА", "value_num": 9.9, "unit": "нг/мл",
             "effective_date": "2026-09-01", "status": "confirmed"},
        ],
        "conflicts": ["psa"],
        "prescriptions": [], "appointments": [], "devices": []})}
    assert "changes" not in s


def test_два_активных_устройства_с_одной_стороны():
    pid = _pid()
    with Session(engine) as s:
        s.add(Device(doctor_id=1, patient_id=pid, kind="stent", side="right", active=True))
        s.add(Device(doctor_id=1, patient_id=pid, kind="stent", side="right", active=True))
        s.commit()
        found = [f for f in find_conflicts(s, pid) if f["rule"] == "C02"]
        assert found and "не закрыли" in found[0]["message"]


def test_проверка_перед_печатью_сообщает_о_конфликте():
    pid = _pid()
    _obs(pid, "psa_warn", 5.0, date(2026, 6, 1))
    _obs(pid, "psa_warn", 8.0, date(2026, 6, 1))
    w = c.get(f"/api/patients/{pid}/handout-check").json()["warnings"]
    assert any("psa_warn" in x for x in w)
