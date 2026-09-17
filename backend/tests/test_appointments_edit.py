"""Приёмы: перенос на другую дату/время и правка причины."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _appt():
    pid = c.get("/api/patients").json()[0]["id"]
    return c.post("/api/appointments", json={"patient_id": pid, "starts_at": "2026-09-10T09:30:00",
                                             "kind": "repeat", "reason": "контроль"}).json()["id"]


def test_reschedule_datetime():
    aid = _appt()
    r = c.patch(f"/api/appointments/{aid}", json={"starts_at": "2026-09-12T14:15:00"}).json()
    assert r["day"] == "2026-09-12" and r["time"] == "14:15"


def test_edit_reason_and_kind():
    aid = _appt()
    r = c.patch(f"/api/appointments/{aid}", json={"reason": "первичный осмотр", "kind": "primary"}).json()
    assert r["reason"] == "первичный осмотр" and r["kind"] == "primary"


def test_reschedule_date_only_defaults_time():
    aid = _appt()
    r = c.patch(f"/api/appointments/{aid}", json={"starts_at": "2026-09-15"}).json()
    assert r["day"] == "2026-09-15" and r["time"] == "09:00"
