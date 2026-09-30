"""Выдача доступа врачу из админки.

Пока оплата не подключена, а пробного периода нет, доступ выдаётся руками.
Раньше это делали вставкой в базу через psql прямо на боевом сервере — не та
операция, которую стоит выполнять руками.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed
from app.db import engine
from app.models import Doctor
from app.services.billing import subscription_ok

seed.run()
c = TestClient(app)
AH = {"x-admin-token": "dev-admin-token"}


def _fresh_doctor(email="grant@test.local"):
    with Session(engine) as s:
        d = Doctor(email=email, full_name="Тестов Тест", specialty="Уролог")
        s.add(d); s.commit()
        return d.id


def test_выдать_доступ():
    did = _fresh_doctor("grant1@test.local")
    with Session(engine) as s:
        assert subscription_ok(s, did) is False

    r = c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 30})
    assert r.status_code == 200, r.text
    assert r.json()["days"] == 30
    assert r.json()["extended"] is False

    with Session(engine) as s:
        assert subscription_ok(s, did) is True


def test_продление_добавляет_к_текущему_сроку():
    """Повторная выдача не обнуляет остаток, а продлевает от текущего конца."""
    did = _fresh_doctor("grant2@test.local")
    first = c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 10}).json()
    second = c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 10}).json()
    assert second["extended"] is True
    assert second["until"] > first["until"]


def test_отозвать_доступ():
    did = _fresh_doctor("grant3@test.local")
    c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 30})
    r = c.delete(f"/api/admin/doctors/{did}/subscription", headers=AH)
    assert r.status_code == 200 and r.json()["changed"] is True
    with Session(engine) as s:
        assert subscription_ok(s, did) is False
    # повторный отзыв не ломается
    assert c.delete(f"/api/admin/doctors/{did}/subscription", headers=AH).json()["changed"] is False


def test_проверки_ввода():
    did = _fresh_doctor("grant4@test.local")
    assert c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 0}).status_code == 400
    assert c.post(f"/api/admin/doctors/{did}/subscription", headers=AH, json={"days": 99999}).status_code == 400
    assert c.post("/api/admin/doctors/999999/subscription", headers=AH, json={"days": 30}).status_code == 404


def test_без_админ_токена_нельзя():
    did = _fresh_doctor("grant5@test.local")
    assert c.post(f"/api/admin/doctors/{did}/subscription", json={"days": 30}).status_code == 401
    assert c.delete(f"/api/admin/doctors/{did}/subscription").status_code == 401
