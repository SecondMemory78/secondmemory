"""Парольная политика: регистрация и сброс отклоняют слабые пароли (152-ФЗ)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def test_register_rejects_short_password():
    r = c.post("/api/auth/register", json={"email": "short@x.ru", "phone": "+79005550001",
                                           "password": "a1b2", "full_name": "T"})
    assert r.status_code == 400


def test_register_rejects_common_password():
    r = c.post("/api/auth/register", json={"email": "common@x.ru", "phone": "+79005550002",
                                           "password": "password", "full_name": "T"})
    assert r.status_code == 400


def test_register_accepts_strong_password():
    r = c.post("/api/auth/register", json={"email": "strong@x.ru", "phone": "+79005550003",
                                           "password": "S3cure-pass", "full_name": "T"})
    assert r.status_code == 200
