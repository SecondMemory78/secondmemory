"""T5. Визит: записи, внесённые при открытом визите, привязываются к нему;
история показывает, что внесли; закрытие завершает визит."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def test_start_reuses_open_encounter():
    pid = _pid()
    e1 = c.post(f"/api/patients/{pid}/encounters", json={"reason": "приём"}).json()
    e2 = c.post(f"/api/patients/{pid}/encounters", json={}).json()
    assert e1["id"] == e2["id"]                       # один открытый визит
    assert c.get(f"/api/patients/{pid}/encounters/active").json()["id"] == e1["id"]


def test_records_attach_to_active_encounter():
    pid = _pid()
    e = c.post(f"/api/patients/{pid}/encounters", json={}).json()
    c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы на никтурию"})
    det = c.get(f"/api/encounters/{e['id']}").json()
    assert any("никтурию" in n["text"] for n in det["notes"])
    assert c.get(f"/api/patients/{pid}/encounters").json()[0]["summary"]["notes"] >= 1


def test_close_encounter():
    pid = _pid()
    e = c.post(f"/api/patients/{pid}/encounters", json={}).json()
    c.post(f"/api/encounters/{e['id']}/close")
    assert c.get(f"/api/patients/{pid}/encounters/active").json() in (None, {})
