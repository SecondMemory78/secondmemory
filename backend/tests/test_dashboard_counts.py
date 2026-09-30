"""Счётчики на Главной считают то же, что показывает список.

Врач видел «на этой неделе: 8 приёмов» при одном живом: список приёмов
отбрасывает отменённые, а счётчик их считал.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed, clock
from app.db import engine
from app.models import Appointment

seed.run()
c = TestClient(app)


def _appt(day_offset, status="planned"):
    with Session(engine) as s:
        pid = c.get("/api/patients").json()[0]["id"]
        a = Appointment(doctor_id=1, patient_id=pid, kind="repeat", reason="контроль",
                        starts_at=clock.now() + timedelta(days=day_offset), status=status)
        s.add(a); s.commit()
        return a.id


def test_отменённые_приёмы_не_считаются():
    before = c.get("/api/dashboard").json()["weekly"]["appointments"]
    _appt(0, status="cancelled")
    _appt(0, status="cancelled")
    after = c.get("/api/dashboard").json()["weekly"]["appointments"]
    assert after == before, "отменённые приёмы попали в счётчик"


def test_живой_приём_считается():
    before = c.get("/api/dashboard").json()["weekly"]["appointments"]
    _appt(0)
    assert c.get("/api/dashboard").json()["weekly"]["appointments"] == before + 1


def test_счётчик_совпадает_со_списком():
    """Главное: цифра и список должны говорить одно и то же."""
    wk0, wk1 = clock.week_bounds()
    listed = [a for a in c.get(f"/api/appointments?date_from={wk0}&date_to={wk1}").json()]
    counted = c.get("/api/dashboard").json()["weekly"]["appointments"]
    assert counted == len(listed), f"счётчик {counted}, в списке {len(listed)}"


def test_сегодняшний_счётчик_тоже_без_отменённых():
    before = c.get("/api/dashboard").json()["today_appointments"]
    _appt(0, status="cancelled")
    assert c.get("/api/dashboard").json()["today_appointments"] == before
