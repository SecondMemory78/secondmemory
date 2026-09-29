"""Управление сессиями врача: список устройств, отзыв конкретной сессии."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _login(email, dev):
    c.post("/api/auth/register", json={"email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7),
                                       "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": dev}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": dev}).json()
    return v["token"]


def test_sessions_list_marks_current_and_revoke():
    t1 = _login("multi@x.ru", "phone")
    t2 = _login("multi@x.ru", "tablet")   # тот же врач, второе устройство
    H2 = {"Authorization": "Bearer " + t2}
    sess = c.get("/api/auth/sessions", headers=H2).json()
    assert len(sess) >= 2
    cur = [x for x in sess if x["current"]]
    assert len(cur) == 1                       # ровно одно помечено текущим (t2)
    # отзываем ПЕРВОЕ устройство (phone) со второго
    other = [x for x in sess if not x["current"]][0]
    c.post(f"/api/auth/sessions/{other['id']}/revoke", headers=H2)
    # токен t1 больше не работает
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer " + t1}).status_code == 401
    # t2 продолжает работать
    assert c.get("/api/auth/me", headers=H2).status_code == 200


def test_cannot_revoke_foreign_session():
    ta = _login("aa@x.ru", "d")
    tb = _login("bb@x.ru", "d")
    sb = c.get("/api/auth/sessions", headers={"Authorization": "Bearer " + tb}).json()[0]
    # врач A пытается отозвать сессию врача B — не должно сработать
    c.post(f"/api/auth/sessions/{sb['id']}/revoke", headers={"Authorization": "Bearer " + ta})
    assert c.get("/api/auth/me", headers={"Authorization": "Bearer " + tb}).status_code == 200
