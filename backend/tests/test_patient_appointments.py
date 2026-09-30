"""Записи на приём видны в карте пациента, на вкладке «Визиты».

Раньше там были только эпизоды, заведённые вручную, а записи из календаря
туда не попадали: врач открывал «Визиты» и видел половину истории.
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
from app.models import Appointment, Patient

seed.run()
c = TestClient(app)


def _patient():
    return c.get("/api/patients").json()[0]["id"]


def test_приёмы_пациента_видны():
    pid = _patient()
    with Session(engine) as s:
        s.add(Appointment(doctor_id=1, patient_id=pid, kind="primary", reason="первичный приём",
                          starts_at=clock.now() - timedelta(days=30), status="done"))
        s.add(Appointment(doctor_id=1, patient_id=pid, kind="repeat", reason="контроль PSA",
                          starts_at=clock.now() + timedelta(days=7), status="planned"))
        s.commit()

    r = c.get(f"/api/patients/{pid}/appointments")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 2
    # сверху — самые свежие
    assert items[0]["starts_at"] > items[-1]["starts_at"]
    future = [i for i in items if not i["past"]]
    past = [i for i in items if i["past"]]
    assert future and past
    assert future[0]["status_label"] == "запланирован"
    assert past[0]["status_label"] in ("состоялся", "запланирован", "не пришёл", "отменён")
    assert past[0]["kind_label"] in ("первичный", "повторный")


def test_чужой_пациент_не_отдаётся():
    with Session(engine) as s:
        other = Patient(doctor_id=999, last_name="Чужой", first_name="", middle_name="")
        s.add(other); s.commit()
        oid = other.id
    assert c.get(f"/api/patients/{oid}/appointments").status_code == 404
    assert c.get("/api/patients/999999/appointments").status_code == 404
