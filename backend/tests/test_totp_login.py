"""TOTP при входе: код из приложения пускает; email-код остаётся резервом;
disable требует подтверждения; после disable TOTP не действует."""
import os, tempfile, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed, totp
from app.db import engine
from app.models import Doctor, LoginCode
from app.services import ratelimit
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _fresh_enabled():
    """Врач с включённым TOTP. Возвращает (email, headers, secret)."""
    em = f"tl_{uuid.uuid4().hex[:8]}@x.ru"
    ph = "+7900" + uuid.uuid4().hex[:7].translate(str.maketrans("abcdef", "012345"))
    c.post("/api/auth/register", json={"email": em, "phone": ph, "password": "goodpass1", "full_name": "T"})
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "d0"})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == em).order_by(LoginCode.id.desc())).first()
    v = c.post("/api/auth/verify", json={"email": em, "code": lc.code, "device_id": "d0"}).json()
    h = {"Authorization": "Bearer " + v["token"]}
    secret = c.post("/api/auth/totp/setup", headers=h).json()["secret"]
    c.post("/api/auth/totp/activate", headers=h, json={"code": totp.totp_now(secret)})
    return em, h, secret


def _new_device_login(em, code, dev):
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": dev})
    return c.post("/api/auth/verify", json={"email": em, "code": code, "device_id": dev})


def test_login_with_totp_code():
    em, h, secret = _fresh_enabled()
    r = _new_device_login(em, totp.totp_now(secret), "dTOTP")
    assert r.status_code == 200 and "token" in r.json()


def test_email_code_still_works_as_fallback():
    em, h, secret = _fresh_enabled()
    # берём email-код (резерв) вместо TOTP
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "dMail"})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == em).order_by(LoginCode.id.desc())).first()
    r = c.post("/api/auth/verify", json={"email": em, "code": lc.code, "device_id": "dMail"})
    assert r.status_code == 200 and "token" in r.json()


def test_disable_requires_code_then_totp_stops_working():
    em, h, secret = _fresh_enabled()
    # неверный код не отключает
    assert c.post("/api/auth/totp/disable", headers=h, json={"code": "000000"}).status_code == 401
    # верный TOTP-код отключает
    r = c.post("/api/auth/totp/disable", headers=h, json={"code": totp.totp_now(secret)})
    assert r.status_code == 200 and r.json()["totp_enabled"] is False
    # теперь TOTP-код на входе больше не пускает (нужен email-код)
    r2 = _new_device_login(em, totp.totp_now(secret), "dAfter")
    assert r2.status_code == 401
