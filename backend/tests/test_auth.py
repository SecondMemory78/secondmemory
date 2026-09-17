"""T4. Аутентификация и шов current_doctor: вход по коду, токен, изоляция врачей."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _register_and_login(email):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone, "password": "pass12345",
                                       "full_name": "Тест Врач", "specialty": "Уролог"})
    # новый пользователь → вход требует код
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "dev1"}).json()
    assert r["code_required"] is True
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "dev1"}).json()
    token = v["token"]
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers={"Authorization": f"Bearer {token}"})
    return token


def test_wrong_password_rejected():
    c.post("/api/auth/register", json={"email": "a@x.ru", "phone": "+79000408789", "password": "right12345", "full_name": "A"})
    assert c.post("/api/auth/login", json={"email": "a@x.ru", "phone": "+79000148095", "password": "wrong"}).status_code == 401


def test_verify_issues_token_and_me():
    token = _register_and_login("me@x.ru")
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "me@x.ru" and me["role"] == "doctor"


def test_known_device_skips_code():
    c.post("/api/auth/register", json={"email": "d@x.ru", "phone": "+79007486383", "password": "pass12345", "full_name": "D"})
    r1 = c.post("/api/auth/login", json={"email": "d@x.ru", "phone": "+79007633959", "password": "pass12345", "device_id": "dd"}).json()
    c.post("/api/auth/verify", json={"email": "d@x.ru", "phone": "+79001359291", "code": r1["dev_code"], "device_id": "dd"})
    # повторный вход с того же устройства — без кода
    r2 = c.post("/api/auth/login", json={"email": "d@x.ru", "phone": "+79007633959", "password": "pass12345", "device_id": "dd"}).json()
    assert r2["code_required"] is False and "token" in r2


def test_current_doctor_scopes_patients():
    t1 = _register_and_login("doc1@x.ru")
    t2 = _register_and_login("doc2@x.ru")
    # врач1 создаёт пациента под своим токеном
    c.post("/api/patients", json={"last_name": "Приватный", "first_name": "Пациент"},
           headers={"Authorization": f"Bearer {t1}"})
    names1 = [p["last_name"] for p in c.get("/api/patients", headers={"Authorization": f"Bearer {t1}"}).json()]
    names2 = [p["last_name"] for p in c.get("/api/patients", headers={"Authorization": f"Bearer {t2}"}).json()]
    assert "Приватный" in names1 and "Приватный" not in names2
