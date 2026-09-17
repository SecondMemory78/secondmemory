"""Security-заголовки и анти-брутфорс входа."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def test_security_headers_present():
    h = c.get("/api/health").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert "content-security-policy" in h and "referrer-policy" in h


def test_login_bruteforce_blocked():
    c.post("/api/auth/register", json={"email": "bf@x.ru", "phone": "+79007140394", "password": "correct12345", "full_name": "BF"})
    codes = []
    for _ in range(12):
        codes.append(c.post("/api/auth/login", json={"email": "bf@x.ru", "phone": "+79006078324", "password": "wrong"}).status_code)
    assert 401 in codes and codes[-1] == 429            # после серии попыток — блок


def test_verify_bruteforce_blocked():
    c.post("/api/auth/register", json={"email": "bf2@x.ru", "phone": "+79004095528", "password": "correct12345", "full_name": "BF2"})
    r = c.post("/api/auth/login", json={"email": "bf2@x.ru", "phone": "+79009152212", "password": "correct12345", "device_id": "d"}).json()
    codes = [c.post("/api/auth/verify", json={"email": "bf2@x.ru", "phone": "+79007246142", "code": "000000", "device_id": "d"}).status_code for _ in range(7)]
    assert codes[-1] == 429                             # подбор кода блокируется


def test_correct_login_resets_counter():
    c.post("/api/auth/register", json={"email": "ok@x.ru", "phone": "+79004901956", "password": "correct12345", "full_name": "OK"})
    for _ in range(3):
        c.post("/api/auth/login", json={"email": "ok@x.ru", "phone": "+79005826364", "password": "wrong"})
    # верный пароль проходит и сбрасывает счётчик
    r = c.post("/api/auth/login", json={"email": "ok@x.ru", "phone": "+79007745240", "password": "correct12345", "device_id": "d"})
    assert r.status_code == 200
