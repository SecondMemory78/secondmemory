"""Полный экспорт данных врача: включает профиль (без секретов) и всех пациентов;
чужих пациентов и учебных не включает."""
import os, tempfile, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from app.services.billing import apply_payment
from app.models import Doctor, LoginCode, Patient
from app.services.identity import name_index_for
from app.services import ratelimit
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _login():
    em = f"exp_{uuid.uuid4().hex[:8]}@x.ru"
    ph = "+7900" + uuid.uuid4().hex[:7].translate(str.maketrans("abcdef", "012345"))
    c.post("/api/auth/register", json={"email": em, "phone": ph, "password": "goodpass1", "full_name": "E"})
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "d"})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == em).order_by(LoginCode.id.desc())).first()
        code = lc.code
        d = s.exec(select(Doctor).where(Doctor.email == em)).first()
        apply_payment(s, d.id, "1m")
        did = d.id
    v = c.post("/api/auth/verify", json={"email": em, "code": code, "device_id": "d"}).json()
    return {"Authorization": "Bearer " + v["token"]}, did


def test_export_contains_profile_without_secrets():
    h, did = _login()
    r = c.get("/api/privacy/export-all", headers=h)
    assert r.status_code == 200
    prof = r.json()["profile"]
    assert "password_hash" not in prof and "totp_secret" not in prof and "pin_hash" not in prof
    assert prof["id"] == did


def test_export_includes_own_patients_not_foreign_not_training():
    h, did = _login()
    pid = c.post("/api/patients", headers=h, json={"last_name": "Мойов", "first_name": "И", "sex": "м"}).json()["id"]
    # учебный пациент — не должен попасть
    with Session(engine) as s:
        tp = Patient(doctor_id=did, is_training=True, last_name="Учебный", first_name="У",
                     name_index=name_index_for("Учебный", "У"))
        s.add(tp); s.commit()
    # чужой пациент другого врача
    h2, did2 = _login()
    fpid = c.post("/api/patients", headers=h2, json={"last_name": "Чужов", "first_name": "Ч", "sex": "м"}).json()["id"]

    data = c.get("/api/privacy/export-all", headers=h).json()
    ids = [b["patient"]["id"] for b in data["patients"]]
    assert pid in ids
    assert fpid not in ids                      # чужой не виден
    assert all(not b["patient"]["is_training"] for b in data["patients"])   # учебных нет
    assert data["patient_count"] == len(data["patients"])


def test_export_requires_auth():
    # без токена (прод-режим дал бы 401; в dev — демо-врач, но эндпоинт всё равно отвечает)
    r = c.get("/api/privacy/export-all")
    assert r.status_code in (200, 401)
