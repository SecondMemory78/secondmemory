"""Демо — одноразовая личная витрина: у каждого посетителя свой аккаунт со
своей копией данных, правки не видят другие, ассистент отключён, старые
аккаунты удаляются целиком."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Doctor, Patient
from app.services.demo import purge_expired_demos, DEMO_TTL, is_disposable_demo
from app import clock
seed.run()
c = TestClient(app)


def _demo():
    r = c.post("/api/auth/demo").json()
    return {"Authorization": "Bearer " + r["token"]}, r


def test_each_visitor_gets_own_demo_doctor():
    h1, r1 = _demo()
    h2, r2 = _demo()
    assert r1["doctor"]["id"] != r2["doctor"]["id"]       # разные аккаунты
    assert r1["demo"] is True and r1["demo_expires_in_minutes"] == 60


def test_demo_has_its_own_copy_of_data():
    h1, _ = _demo()
    h2, _ = _demo()
    a = c.get("/api/patients", headers=h1).json()
    b = c.get("/api/patients", headers=h2).json()
    assert len(a) >= 3 and len(b) >= 3                    # у каждого своя заполненная база
    assert {p["id"] for p in a}.isdisjoint({p["id"] for p in b})


def test_changes_in_one_demo_are_invisible_to_another():
    h1, _ = _demo()
    h2, _ = _demo()
    c.post("/api/patients", headers=h1, json={"last_name": "Следов", "first_name": "Тест"})
    names = [f"{p['last_name']}" for p in c.get("/api/patients", headers=h2).json()]
    assert "Следов" not in names                          # чужие правки не видны


def test_assistant_blocked_in_demo():
    h, _ = _demo()
    r = c.post("/api/assistant/command", headers=h, json={"text": "напомни позвонить"})
    assert r.status_code == 403 and "демо" in r.json()["detail"].lower()


def test_assistant_works_for_real_account():
    c.post("/api/auth/register", json={"email": "demo_real@x.ru", "phone": "+79000007777",
                                       "password": "pass12345", "full_name": "Настоящий"})
    lg = c.post("/api/auth/login", json={"email": "demo_real@x.ru", "password": "pass12345",
                                         "device_id": "d"}).json()
    vf = c.post("/api/auth/verify", json={"email": "demo_real@x.ru", "code": lg["dev_code"],
                                          "device_id": "d"}).json()
    h = {"Authorization": "Bearer " + vf["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    assert c.post("/api/assistant/command", headers=h,
                  json={"text": "напомни позвонить"}).status_code == 200


def test_expired_demo_is_purged_with_its_data():
    h, r = _demo()
    did = r["doctor"]["id"]
    with Session(engine) as s:
        d = s.get(Doctor, did)
        assert is_disposable_demo(d)
        d.created_at = clock.now() - DEMO_TTL - timedelta(minutes=5)   # состарим
        s.add(d); s.commit()
        # и погасим его сессии, иначе живой аккаунт не трогаем
        from app.models import AuthSession
        for a in s.exec(select(AuthSession).where(AuthSession.doctor_id == did)).all():
            a.expires_at = clock.now() - timedelta(minutes=1); s.add(a)
        s.commit()
        removed = purge_expired_demos(s)
        assert removed >= 1
        assert s.get(Doctor, did) is None                               # врача нет
        assert not s.exec(select(Patient).where(Patient.doctor_id == did)).all()  # и данных нет


def test_live_demo_is_not_purged():
    h, r = _demo()
    did = r["doctor"]["id"]
    with Session(engine) as s:
        d = s.get(Doctor, did)
        d.created_at = clock.now() - DEMO_TTL - timedelta(minutes=5)
        s.add(d); s.commit()
        purge_expired_demos(s)                       # сессия жива → не удаляем
        assert s.get(Doctor, did) is not None
    assert c.get("/api/patients", headers=h).status_code == 200
