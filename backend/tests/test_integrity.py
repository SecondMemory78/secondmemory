"""Детерминированный контроль целостности карты (D-правила без ИИ)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def _patient(dob="1980-05-05"):
    pid = c.post("/api/patients", headers=H, json={"last_name": "Целостнов", "first_name": "Ц", "birth_date": dob}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H)
    return pid


def _find(pid):
    return c.get(f"/api/patients/{pid}/integrity", headers=H).json()


def test_clean_card_no_findings():
    pid = _patient()
    c.post(f"/api/patients/{pid}/observations", headers=H,
           json={"parameter_code": "psa_total", "value_num": 3.2, "unit": "нг/мл",
                 "effective_date": "2026-01-10", "status": "confirmed"})
    assert _find(pid)["count"] == 0


def test_D02_date_before_birth():
    pid = _patient(dob="2000-01-01")
    c.post(f"/api/patients/{pid}/observations", headers=H,
           json={"parameter_code": "psa_total", "value_num": 3.0, "unit": "нг/мл",
                 "effective_date": "1990-06-06", "status": "confirmed"})
    rules = [f["rule"] for f in _find(pid)["findings"]]
    assert "D02" in rules


def test_D02_future_date():
    pid = _patient()
    future = (clock.today() + timedelta(days=30)).isoformat()
    c.post(f"/api/patients/{pid}/observations", headers=H,
           json={"parameter_code": "psa_total", "value_num": 3.0, "unit": "нг/мл",
                 "effective_date": future, "status": "confirmed"})
    assert any(f["rule"] == "D02" and "будущем" in f["message"] for f in _find(pid)["findings"])


def test_D05_negative_value():
    pid = _patient()
    c.post(f"/api/patients/{pid}/observations", headers=H,
           json={"parameter_code": "psa_total", "value_num": -1.0, "unit": "нг/мл",
                 "effective_date": "2026-01-10", "status": "confirmed"})
    assert any(f["rule"] == "D05" for f in _find(pid)["findings"])


def test_I_missing_unit():
    pid = _patient()
    c.post(f"/api/patients/{pid}/observations", headers=H,
           json={"parameter_code": "psa_total", "value_num": 3.0, "unit": "",
                 "effective_date": "2026-01-10", "status": "confirmed"})
    assert any(f["level"] == "I" for f in _find(pid)["findings"])


def test_D02_discharge_before_admission():
    pid = _patient()
    adm = clock.now().isoformat()
    c.post(f"/api/patients/{pid}/episodes", headers=H, json={
        "type": "hospitalization", "actual_admission_at": adm})
    # выписываем задним числом (раньше поступления) через PATCH эпизода
    ep = c.get(f"/api/patients/{pid}/episodes", headers=H).json()["items"][0]
    before = (clock.now() - timedelta(days=3)).isoformat()
    c.patch(f"/api/episodes/{ep['id']}", headers=H,
            json={"expected_version": ep["version"], "actual_discharge_at": before})
    assert any(f["rule"] == "D02" and "оступлени" in f["message"] for f in _find(pid)["findings"])
