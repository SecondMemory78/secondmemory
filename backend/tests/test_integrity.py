"""Детерминированный контроль целостности карты (D-правила без ИИ)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.db import engine
from app.models import Device, Prescription
from sqlmodel import Session
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


def _doctor_id_of(pid):
    with Session(engine) as s:
        from app.models import Patient
        return s.get(Patient, pid).doctor_id


def test_d03_device_closed_before_installed():
    pid = _patient()
    did = _doctor_id_of(pid)
    with Session(engine) as s:
        s.add(Device(doctor_id=did, patient_id=pid, kind="stent", active=False,
                     installed_at=clock.today(), closed_at=clock.today() - timedelta(days=5),
                     closed_action="removed"))
        s.commit()
    rules = [f["rule"] for f in _find(pid)["findings"]]
    assert "D03" in rules


def test_d03_active_but_closed():
    pid = _patient()
    did = _doctor_id_of(pid)
    with Session(engine) as s:
        s.add(Device(doctor_id=did, patient_id=pid, kind="catheter", active=True,
                     closed_at=clock.today()))     # противоречие: активно и закрыто
        s.commit()
    rules = [f["rule"] for f in _find(pid)["findings"]]
    assert "D03" in rules


def test_q02_same_inn_two_prescriptions():
    pid = _patient()
    with Session(engine) as s:
        # Омник и Профлосин — оба бренды тамсулозина (по справочнику)
        s.add(Prescription(patient_id=pid, drug_name="Омник"))
        s.add(Prescription(patient_id=pid, drug_name="Профлосин"))
        s.commit()
    findings = _find(pid)["findings"]
    q02 = [f for f in findings if f["rule"] == "Q02"]
    assert len(q02) >= 1 and q02[0]["level"] == "Q"


def test_q02_no_false_positive_different_drugs():
    pid = _patient()
    with Session(engine) as s:
        s.add(Prescription(patient_id=pid, drug_name="Тамсулозин"))
        s.add(Prescription(patient_id=pid, drug_name="Силодозин"))   # другое МНН
        s.commit()
    rules = [f["rule"] for f in _find(pid)["findings"]]
    assert "Q02" not in rules


def test_q02_cancelled_not_counted_as_active_duplicate():
    pid = _patient()
    with Session(engine) as s:
        s.add(Prescription(patient_id=pid, drug_name="Омник", status="active"))
        s.add(Prescription(patient_id=pid, drug_name="Профлосин", status="cancelled",
                           cancelled_at=clock.now()))
        s.commit()
    findings = _find(pid)["findings"]
    q02 = [f for f in findings if f["rule"] == "Q02"]
    # НЕ должно быть «двух актуальных» (одно отменено); должен быть сигнал active+cancelled
    assert not any("актуальных" in f["message"] for f in q02)
    assert any("активным, и отменённым" in f["message"] for f in q02)


def test_cancel_prescription_endpoint():
    pid = _patient()
    with Session(engine) as s:
        p = Prescription(patient_id=pid, drug_name="Тамсулозин", status="active")
        s.add(p); s.commit(); s.refresh(p); rx_id = p.id
    r = c.post(f"/api/prescriptions/{rx_id}/cancel", headers=H)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # повторная отмена → 409
    assert c.post(f"/api/prescriptions/{rx_id}/cancel", headers=H).status_code == 409
    # в списке видно отменённое
    lst = c.get(f"/api/patients/{pid}/prescriptions", headers=H).json()["items"]
    assert any(x["id"] == rx_id and x["status"] == "cancelled" for x in lst)


def _set_allergy(pid, detail):
    c.put(f"/api/patients/{pid}/safety", headers=H,
          json={"kind": "allergy", "state": "present", "detail": detail})


def test_q01_active_rx_conflicts_with_allergy():
    pid = _patient()
    _set_allergy(pid, "тамсулозин")
    with Session(engine) as s:
        s.add(Prescription(patient_id=pid, drug_name="Омник", status="active"))  # бренд тамсулозина
        s.commit()
    findings = _find(pid)["findings"]
    q01 = [f for f in findings if f["rule"] == "Q01"]
    assert len(q01) >= 1 and q01[0]["level"] == "Q"


def test_q01_no_conflict_when_no_allergy():
    pid = _patient()
    with Session(engine) as s:
        s.add(Prescription(patient_id=pid, drug_name="Омник", status="active"))
        s.commit()
    assert "Q01" not in [f["rule"] for f in _find(pid)["findings"]]


def test_q01_cancelled_rx_not_flagged():
    pid = _patient()
    _set_allergy(pid, "тамсулозин")
    with Session(engine) as s:
        s.add(Prescription(patient_id=pid, drug_name="Омник", status="cancelled",
                           cancelled_at=clock.now()))
        s.commit()
    assert "Q01" not in [f["rule"] for f in _find(pid)["findings"]]
