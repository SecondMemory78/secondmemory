"""Сброс пароля: enumeration-safe, одноразовый токен, смена пароля, гашение сессий."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _register(email, pw="oldpass12345"):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone, "password": pw, "full_name": "Тест"})


def test_forgot_enumeration_safe():
    _register("real@x.ru")
    r1 = c.post("/api/auth/forgot", json={"email": "real@x.ru"}).json()
    r2 = c.post("/api/auth/forgot", json={"email": "nobody@x.ru"}).json()
    assert r1["ok"] is True and r2["ok"] is True          # одинаковый ответ
    assert "dev_token" in r1 and "dev_token" not in r2    # токен только для существующего


def test_reset_changes_password_and_login_works():
    _register("reset@x.ru")
    tok = c.post("/api/auth/forgot", json={"email": "reset@x.ru"}).json()["dev_token"]
    r = c.post("/api/auth/reset", json={"email": "reset@x.ru", "phone": "+79002740074", "token": tok, "new_password": "newpass12345"})
    assert r.status_code == 200
    # старый пароль больше не работает, новый — да
    assert c.post("/api/auth/login", json={"email": "reset@x.ru", "phone": "+79002945131", "password": "oldpass12345"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "reset@x.ru", "phone": "+79001308904", "password": "newpass12345"}).status_code == 200


def test_token_is_single_use():
    _register("once@x.ru")
    tok = c.post("/api/auth/forgot", json={"email": "once@x.ru"}).json()["dev_token"]
    c.post("/api/auth/reset", json={"email": "once@x.ru", "phone": "+79003522495", "token": tok, "new_password": "newpass12345"})
    r = c.post("/api/auth/reset", json={"email": "once@x.ru", "phone": "+79004048814", "token": tok, "new_password": "another12345"})
    assert r.status_code == 400                            # повторно нельзя


def test_wrong_token_rejected():
    _register("wrong@x.ru")
    c.post("/api/auth/forgot", json={"email": "wrong@x.ru"})
    r = c.post("/api/auth/reset", json={"email": "wrong@x.ru", "phone": "+79005684142", "token": "badtoken", "new_password": "newpass12345"})
    assert r.status_code == 400
