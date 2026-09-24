"""TOTP enroll: setup выдаёт секрет+URI без включения; activate включает по коду;
неверный код → 401; повторный setup при включённом → 409."""
import os, tempfile, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed, totp
from app.db import engine
from app.services.billing import apply_payment
from app.models import Doctor, LoginCode
from app.services import ratelimit
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _login():
    em = f"totp_{uuid.uuid4().hex[:8]}@x.ru"
    ph = "+7900" + uuid.uuid4().hex[:7].translate(str.maketrans("abcdef", "012345"))
    c.post("/api/auth/register", json={"email": em, "phone": ph, "password": "goodpass1", "full_name": "T"})
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "d"})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == em).order_by(LoginCode.id.desc())).first()
    v = c.post("/api/auth/verify", json={"email": em, "code": lc.code, "device_id": "d"}).json()
    return {"Authorization": "Bearer " + v["token"]}, em


def test_setup_returns_secret_without_enabling():
    h, em = _login()
    r = c.post("/api/auth/totp/setup", headers=h)
    assert r.status_code == 200
    assert r.json()["secret"] and r.json()["otpauth_uri"].startswith("otpauth://")
    assert c.get("/api/auth/totp/status", headers=h).json()["totp_enabled"] is False


def test_activate_with_valid_code_enables():
    h, em = _login()
    secret = c.post("/api/auth/totp/setup", headers=h).json()["secret"]
    code = totp.totp_now(secret)
    r = c.post("/api/auth/totp/activate", headers=h, json={"code": code})
    assert r.status_code == 200 and r.json()["totp_enabled"] is True
    assert c.get("/api/auth/totp/status", headers=h).json()["totp_enabled"] is True


def test_activate_wrong_code_rejected():
    h, em = _login()
    c.post("/api/auth/totp/setup", headers=h)
    r = c.post("/api/auth/totp/activate", headers=h, json={"code": "000000"})
    assert r.status_code == 401
    assert c.get("/api/auth/totp/status", headers=h).json()["totp_enabled"] is False


def test_setup_again_when_enabled_conflicts():
    h, em = _login()
    secret = c.post("/api/auth/totp/setup", headers=h).json()["secret"]
    c.post("/api/auth/totp/activate", headers=h, json={"code": totp.totp_now(secret)})
    r = c.post("/api/auth/totp/setup", headers=h)
    assert r.status_code == 409
