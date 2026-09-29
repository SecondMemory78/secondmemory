"""Резервные коды 2FA: выдаются при активации TOTP, хранятся хэшами,
перевыпуск требует код и заменяет старые, disable их удаляет."""
import os, tempfile, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed, totp
from app.db import engine
from app.models import Doctor, LoginCode, BackupCode
from app.security import sha256_hex
from app.services import ratelimit
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _enable_totp():
    em = f"bc_{uuid.uuid4().hex[:8]}@x.ru"
    ph = "+7900" + uuid.uuid4().hex[:7].translate(str.maketrans("abcdef", "012345"))
    c.post("/api/auth/register", json={"email": em, "phone": ph, "password": "goodpass1", "full_name": "B"})
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "d"})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == em).order_by(LoginCode.id.desc())).first()
    v = c.post("/api/auth/verify", json={"email": em, "code": lc.code, "device_id": "d"}).json()
    h = {"Authorization": "Bearer " + v["token"]}
    secret = c.post("/api/auth/totp/setup", headers=h).json()["secret"]
    act = c.post("/api/auth/totp/activate", headers=h, json={"code": totp.totp_now(secret)}).json()
    return em, h, secret, act


def _did(em):
    with Session(engine) as s:
        return s.exec(select(Doctor).where(Doctor.email == em)).first().id


def test_activation_returns_backup_codes():
    em, h, secret, act = _enable_totp()
    assert len(act["backup_codes"]) == 10
    assert all("-" in code for code in act["backup_codes"])


def test_codes_stored_as_hashes_not_plaintext():
    em, h, secret, act = _enable_totp()
    code0 = act["backup_codes"][0]
    with Session(engine) as s:
        rows = s.exec(select(BackupCode).where(BackupCode.doctor_id == _did(em))).all()
        stored = [r.code_hash for r in rows]
    assert code0 not in stored                       # открытым текстом не лежит
    assert sha256_hex(code0) in stored               # лежит хэш


def test_count_endpoint():
    em, h, secret, act = _enable_totp()
    assert c.get("/api/auth/totp/backup-codes/count", headers=h).json()["remaining"] == 10


def test_regenerate_requires_code_and_replaces():
    em, h, secret, act = _enable_totp()
    old = set(act["backup_codes"])
    assert c.post("/api/auth/totp/backup-codes", headers=h, json={"code": "000000"}).status_code == 401
    r = c.post("/api/auth/totp/backup-codes", headers=h, json={"code": totp.totp_now(secret)})
    assert r.status_code == 200
    new = set(r.json()["backup_codes"])
    assert new.isdisjoint(old)                       # старые заменены
    # старых хэшей в БД больше нет
    with Session(engine) as s:
        stored = {r.code_hash for r in s.exec(select(BackupCode).where(BackupCode.doctor_id == _did(em))).all()}
    assert all(sha256_hex(o) not in stored for o in old)


def test_disable_removes_backup_codes():
    em, h, secret, act = _enable_totp()
    c.post("/api/auth/totp/disable", headers=h, json={"code": totp.totp_now(secret)})
    with Session(engine) as s:
        rows = s.exec(select(BackupCode).where(BackupCode.doctor_id == _did(em))).all()
    assert len(rows) == 0


def _login_with(em, code, dev):
    ratelimit._hits.clear()
    c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": dev})
    return c.post("/api/auth/verify", json={"email": em, "code": code, "device_id": dev})


def test_login_with_backup_code_single_use():
    em, h, secret, act = _enable_totp()
    codes = act["backup_codes"]
    # вход по резервному коду
    r = _login_with(em, codes[0], "dbk1")
    assert r.status_code == 200 and r.json().get("backup_code_used") is True
    # тот же код повторно не пускает (сгорел)
    r2 = _login_with(em, codes[0], "dbk2")
    assert r2.status_code == 401
    # другой код ещё действует
    r3 = _login_with(em, codes[1], "dbk3")
    assert r3.status_code == 200
    # осталось 8 из 10
    assert c.get("/api/auth/totp/backup-codes/count", headers=h).json()["remaining"] == 8
