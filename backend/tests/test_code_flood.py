"""Антифлуд отправки кода на почту: повторный код не чаще cooldown; суточный потолок.
Константы патчим в рантайме (не через env), чтобы не зависеть от conftest."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services import ratelimit
from app.routers import auth as auth_mod
seed.run()
c = TestClient(app)


def test_second_code_within_cooldown_is_throttled(monkeypatch):
    monkeypatch.setattr(auth_mod, "CODE_COOLDOWN", 60)
    ratelimit._hits.clear()
    c.post("/api/auth/register", json={"email": "flood1@x.ru", "phone": "+79001110011",
                                       "password": "floodpass1", "full_name": "F"})
    ratelimit._hits.clear()
    r1 = c.post("/api/auth/login", json={"email": "flood1@x.ru", "password": "floodpass1", "device_id": "d1"})
    assert r1.status_code == 200
    r2 = c.post("/api/auth/login", json={"email": "flood1@x.ru", "password": "floodpass1", "device_id": "d2"})
    assert r2.status_code == 429


def test_daily_cap_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(auth_mod, "CODE_COOLDOWN", 60)
    monkeypatch.setattr(auth_mod, "CODE_DAILY_MAX", 3)
    ratelimit._hits.clear()
    c.post("/api/auth/register", json={"email": "flood2@x.ru", "phone": "+79001110022",
                                       "password": "floodpass1", "full_name": "F"})
    seen429 = False
    for i in range(6):
        ratelimit._hits.pop("code_cooldown:flood2@x.ru", None)   # снимаем паузу, оставляем суточный счётчик
        r = c.post("/api/auth/login", json={"email": "flood2@x.ru", "password": "floodpass1", "device_id": f"x{i}"})
        if r.status_code == 429:
            seen429 = True
            break
    assert seen429, "суточный потолок писем не сработал"


def test_legit_register_then_verify_not_blocked(monkeypatch):
    monkeypatch.setattr(auth_mod, "CODE_COOLDOWN", 60)
    ratelimit._hits.clear()
    r = c.post("/api/auth/register", json={"email": "legit@x.ru", "phone": "+79001110099",
                                           "password": "goodpass1", "full_name": "L"})
    assert r.status_code == 200
    code = r.json().get("dev_code")
    assert code
    v = c.post("/api/auth/verify", json={"email": "legit@x.ru", "code": code, "device_id": "d"})
    assert v.status_code == 200 and "token" in v.json()
