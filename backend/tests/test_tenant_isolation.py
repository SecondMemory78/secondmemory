"""Изоляция врачей: врач B не должен видеть/менять/экспортировать/удалять
карточку пациента врача A (IDOR). RLS на SQLite — no-op, поэтому изоляцию
обязан обеспечивать код роутеров. Ожидаем 404 (не 200 и не 403 — не раскрываем
существование чужой карточки)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from app.services.billing import apply_payment
from app.models import Doctor
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _login(email, dev="d"):
    c.post("/api/auth/register", json={
        "email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7),
        "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": dev}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": dev}).json()
    # активируем подписку, иначе барьер оплаты (402) не даст создавать записи
    with Session(engine) as s:
        d = s.exec(select(Doctor).where(Doctor.email == email)).first()
        apply_payment(s, d.id, "1m")
    return {"Authorization": "Bearer " + v["token"]}


def _make_patient(headers):
    r = c.post("/api/patients", headers=headers, json={
        "last_name": "Тестов", "first_name": "Пётр", "birth_date": "1980-05-01", "sex": "m"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


HA = _login("tenant_a@x.ru")
HB = _login("tenant_b@x.ru")
PID_A = _make_patient(HA)          # пациент принадлежит врачу A


def test_foreign_patient_read_blocked():
    assert c.get(f"/api/patients/{PID_A}", headers=HB).status_code == 404
    assert c.get(f"/api/patients/{PID_A}/timeline", headers=HB).status_code == 404


def test_foreign_episodes_blocked():
    assert c.post(f"/api/patients/{PID_A}/encounters", headers=HB, json={"reason": "x"}).status_code == 404
    assert c.get(f"/api/patients/{PID_A}/episodes", headers=HB).status_code == 404
    assert c.get(f"/api/patients/{PID_A}/encounters", headers=HB).status_code == 404


def test_foreign_encounter_detail_blocked():
    # A открывает эпизод (нужно согласие пациента), B пытается прочитать по его id
    c.post(f"/api/patients/{PID_A}/consent/electronic", headers=HA,
           json={"signer_name": "Тестов Пётр", "agreed": True})
    eid = c.post(f"/api/patients/{PID_A}/encounters", headers=HA, json={"reason": "приём"}).json()["id"]
    assert c.get(f"/api/encounters/{eid}", headers=HB).status_code == 404
    assert c.post(f"/api/encounters/{eid}/close", headers=HB).status_code == 404


def test_foreign_diagnoses_blocked():
    assert c.get(f"/api/patients/{PID_A}/diagnoses", headers=HB).status_code == 404
    assert c.post(f"/api/patients/{PID_A}/diagnoses", headers=HB,
                  json={"code": "N40", "text": "ДГПЖ"}).status_code == 404


def test_foreign_protocol_blocked():
    assert c.get(f"/api/patients/{PID_A}/protocol", headers=HB).status_code == 404


def test_foreign_consent_blocked():
    assert c.get(f"/api/patients/{PID_A}/consent/form", headers=HB).status_code == 404
    assert c.post(f"/api/patients/{PID_A}/consent/electronic", headers=HB,
                  json={"signer_name": "X", "agreed": True}).status_code == 404


def test_foreign_export_blocked():
    assert c.get(f"/api/patients/{PID_A}/export", headers=HB).status_code == 404
    assert c.get(f"/api/patients/{PID_A}/export.pdf", headers=HB).status_code == 404


def test_foreign_erase_blocked():
    pid = _make_patient(HA)                       # отдельный пациент, чтобы не влиять на другие тесты
    assert c.delete(f"/api/patients/{pid}/erase", headers=HB).status_code == 404
    # карточка должна остаться на месте у владельца
    assert c.get(f"/api/patients/{pid}", headers=HA).status_code == 200


def test_owner_still_has_access():
    # регрессия: сам врач A по-прежнему всё видит
    assert c.get(f"/api/patients/{PID_A}", headers=HA).status_code == 200
    assert c.get(f"/api/patients/{PID_A}/episodes", headers=HA).status_code == 200
    assert c.get(f"/api/patients/{PID_A}/consent/form", headers=HA).status_code == 200


def test_foreign_integrity_blocked():
    assert c.get(f"/api/patients/{PID_A}/integrity", headers=HB).status_code == 404


def test_foreign_whats_new_blocked():
    assert c.get(f"/api/patients/{PID_A}/whats-new", headers=HB).status_code == 404


def test_foreign_notes_blocked():
    assert c.get(f"/api/patients/{PID_A}/notes", headers=HB).status_code == 404
    assert c.post(f"/api/patients/{PID_A}/notes?text=x", headers=HB).status_code == 404
    assert c.delete(f"/api/patients/{PID_A}/notes/1", headers=HB).status_code == 404
