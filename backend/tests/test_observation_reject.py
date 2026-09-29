"""Распознанное значение можно отклонить или удалить — врач вправе не согласиться
с тем, что извлёк ИИ. Плюс проверка, что чужие значения недоступны."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _pid():
    pid = c.post("/api/patients", json={"last_name": "Значев", "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    return pid


def _obs(pid, value=9.9, status="pending"):
    r = c.post(f"/api/patients/{pid}/observations",
               json={"parameter_code": "psa_total", "value_num": value,
                     "unit": "нг/мл", "status": status}).json()
    assert "id" in r, f"неожиданный ответ: {r}"
    return r["id"]


def _pending(pid):
    series = c.get(f"/api/patients/{pid}/timeline").json().get("psa_total", [])
    return [x for x in series if x["status"] == "pending"]


def test_reject_removes_from_pending_but_keeps_record():
    pid = _pid()
    oid = _obs(pid)
    assert len(_pending(pid)) == 1
    r = c.post(f"/api/observations/{oid}/reject").json()
    assert r["status"] == "rejected"
    assert _pending(pid) == []                 # из работы ушло


def test_rejected_value_does_not_enter_dynamics():
    pid = _pid()
    oid = _obs(pid)
    c.post(f"/api/observations/{oid}/reject")
    series = c.get(f"/api/patients/{pid}/timeline").json().get("psa_total", [])
    assert all(x["status"] != "confirmed" for x in series)


def test_delete_removes_value_entirely():
    pid = _pid()
    oid = _obs(pid, 4.2, "confirmed")
    assert c.delete(f"/api/observations/{oid}").json()["ok"] is True
    series = c.get(f"/api/patients/{pid}/timeline").json().get("psa_total", [])
    assert not any(x.get("id") == oid for x in series)


def test_foreign_doctor_cannot_touch_values():
    """Раньше подтвердить чужое значение можно было по одному id."""
    pid = _pid()
    oid = _obs(pid)
    c.post("/api/auth/register", json={"email": "obs_other@x.ru", "phone": "+79000005511",
                                       "password": "pass12345", "full_name": "Другой"})
    lg = c.post("/api/auth/login", json={"email": "obs_other@x.ru", "password": "pass12345",
                                         "device_id": "d"}).json()
    vf = c.post("/api/auth/verify", json={"email": "obs_other@x.ru", "code": lg["dev_code"],
                                          "device_id": "d"}).json()
    hb = {"Authorization": "Bearer " + vf["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=hb)
    assert c.post(f"/api/observations/{oid}/confirm", headers=hb).status_code == 404
    assert c.post(f"/api/observations/{oid}/reject", headers=hb).status_code == 404
    assert c.delete(f"/api/observations/{oid}", headers=hb).status_code == 404


def test_missing_value_is_404():
    assert c.post("/api/observations/999999/reject").status_code == 404
    assert c.delete("/api/observations/999999").status_code == 404
