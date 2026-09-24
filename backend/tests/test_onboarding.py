"""Онбординг-песочница: учебный пациент изолирован от рабочих данных,
жизненный цикл (старт/финиш/пропуск), прогресс подсказок, страховочная зачистка."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.db import engine
from app.services.billing import apply_payment
from app.services import onboarding as ob
from app.models import Doctor, Patient
from sqlmodel import Session, select

seed.run()
c = TestClient(app)


def _login(email, dev="d"):
    c.post("/api/auth/register", json={"email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7), "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": dev}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": dev}).json()
    with Session(engine) as s:
        d = s.exec(select(Doctor).where(Doctor.email == email)).first()
        apply_payment(s, d.id, "1m")
    return {"Authorization": "Bearer " + v["token"]}, v["doctor"]["id"]


H, DID = _login("ob_a@x.ru")


def test_progress_initially_empty():
    p = c.get("/api/onboarding/progress", headers=H).json()
    assert p["onboarding_done"] is False
    assert p["tips_seen"] == []


def test_sandbox_start_is_idempotent():
    r1 = c.post("/api/onboarding/sandbox/start", headers=H).json()
    r2 = c.post("/api/onboarding/sandbox/start", headers=H).json()
    assert r1["patient_id"] == r2["patient_id"]        # не плодит дублей
    with Session(engine) as s:
        n = len(s.exec(select(Patient).where(Patient.doctor_id == DID, Patient.is_training == True)).all())
        assert n == 1


def test_training_patient_hidden_from_work_lists():
    c.post("/api/onboarding/sandbox/start", headers=H)
    # обычный список пациентов НЕ содержит учебного
    lst = c.get("/api/patients", headers=H).json()
    ids = [p["id"] for p in (lst if isinstance(lst, list) else lst.get("items", []))]
    with Session(engine) as s:
        tid = s.exec(select(Patient).where(Patient.doctor_id == DID, Patient.is_training == True)).first().id
    assert tid not in ids
    # поиск тёзки не находит учебного (реальный контракт: POST /check-identity)
    chk = c.post("/api/patients/check-identity", headers=H,
                 json={"last_name": "Демонстрационный", "first_name": "Пациент"})
    assert chk.status_code == 200, chk.text
    cands = chk.json().get("candidates", [])
    assert all(cc.get("id") != tid for cc in cands)


def test_finish_deletes_training_and_marks_done():
    c.post("/api/onboarding/sandbox/start", headers=H)
    c.post("/api/onboarding/sandbox/finish", headers=H, json={"completed": True})
    with Session(engine) as s:
        n = len(s.exec(select(Patient).where(Patient.doctor_id == DID, Patient.is_training == True)).all())
        assert n == 0                                   # учебный удалён
    assert c.get("/api/onboarding/progress", headers=H).json()["onboarding_done"] is True


def test_tip_seen_whitelist():
    assert c.post("/api/onboarding/tips/seen", headers=H, json={"key": "tip:protocol"}).status_code == 200
    assert c.post("/api/onboarding/tips/seen", headers=H, json={"key": "tip:bogus"}).status_code == 400
    # идемпотентно — повтор не ломается и не дублирует
    c.post("/api/onboarding/tips/seen", headers=H, json={"key": "tip:protocol"})
    seen = c.get("/api/onboarding/progress", headers=H).json()["tips_seen"]
    assert seen.count("tip:protocol") == 1


def test_sweep_removes_stale_training_only():
    # свежий врач; создаём учебного и «старим» его на 2 суток
    h2, did2 = _login("ob_b@x.ru")
    c.post("/api/onboarding/sandbox/start", headers=h2)
    with Session(engine) as s:
        tp = s.exec(select(Patient).where(Patient.doctor_id == did2, Patient.is_training == True)).first()
        tp.created_at = clock.now() - timedelta(hours=48); s.add(tp); s.commit()
        removed = ob.sweep_stale_training(s); s.commit()
    assert removed >= 1
    with Session(engine) as s:
        assert s.exec(select(Patient).where(Patient.doctor_id == did2, Patient.is_training == True)).first() is None


def test_sweep_keeps_fresh_training():
    h3, did3 = _login("ob_c@x.ru")
    c.post("/api/onboarding/sandbox/start", headers=h3)   # свежий, не старим
    with Session(engine) as s:
        ob.sweep_stale_training(s); s.commit()
        assert s.exec(select(Patient).where(Patient.doctor_id == did3, Patient.is_training == True)).first() is not None
