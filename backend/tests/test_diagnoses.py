"""T6. Множественные диагнозы: основной в кэше, смена основного, снятие с историей."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _new_patient():
    pid = c.post("/api/patients", json={"last_name": "Диагнозов", "first_name": "Тест"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})  # без согласия карта заблокирована
    return pid


def test_first_diagnosis_is_primary_and_cached():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40.0", "title": "ДГПЖ"})
    p = c.get(f"/api/patients/{pid}").json()
    assert p["diagnosis_code"] == "N40.0"
    lst = c.get(f"/api/patients/{pid}/diagnoses").json()
    assert len(lst) == 1 and lst[0]["is_primary"] is True


def test_switch_primary_updates_cache():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40.0", "title": "ДГПЖ"})
    d2 = c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N41.1", "title": "Хр. простатит"}).json()
    assert d2["is_primary"] is False
    c.post(f"/api/patients/{pid}/diagnoses/{d2['id']}/primary")
    assert c.get(f"/api/patients/{pid}").json()["diagnosis_code"] == "N41.1"
    actives = [d for d in c.get(f"/api/patients/{pid}/diagnoses").json() if d["status"] == "active"]
    assert sum(1 for d in actives if d["is_primary"]) == 1


def test_remove_keeps_history_and_reassigns_primary():
    pid = _new_patient()
    d1 = c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40.0", "title": "ДГПЖ"}).json()
    c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N41.1", "title": "Простатит"})
    c.post(f"/api/patients/{pid}/diagnoses/{d1['id']}/remove")
    lst = c.get(f"/api/patients/{pid}/diagnoses").json()
    assert any(d["status"] == "removed" for d in lst)            # история сохранена
    actives = [d for d in lst if d["status"] == "active"]
    assert len(actives) == 1 and actives[0]["is_primary"] is True  # основной переназначен
    assert c.get(f"/api/patients/{pid}").json()["diagnosis_code"] == "N41.1"
