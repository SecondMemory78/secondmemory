"""Админ/поддержка: карточки врачей + сброс пароля (Уровень 1 — без данных пациентов)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"x-admin-token": "dev-admin-token"}


def _make_doctor(email):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone,
                                       "password": "pass12345", "full_name": "Иван Тестов"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
    return {"Authorization": "Bearer " + v["token"]}, v["doctor"]["id"]


def test_admin_doctors_requires_token():
    assert c.get("/api/admin/doctors").status_code == 401


def test_admin_doctors_list_and_search():
    _make_doctor("adm_list@x.ru")
    rows = c.get("/api/admin/doctors", headers=H).json()
    assert any(d["email"] == "adm_list@x.ru" for d in rows)
    # поиск по почте
    found = c.get("/api/admin/doctors?q=adm_list", headers=H).json()
    assert len(found) >= 1 and all("adm_list" in (d["email"] + d["full_name"]).lower() for d in found)
    # в списке нет ничего про пациентов — только аккаунт врача
    keys = set(rows[0].keys())
    assert "patients" not in keys and "observations" not in keys


def test_admin_doctor_detail_has_devices_no_patient_data():
    _, did = _make_doctor("adm_detail@x.ru")
    d = c.get(f"/api/admin/doctors/{did}", headers=H).json()
    assert d["email"] == "adm_detail@x.ru"
    assert "devices" in d and "active_sessions" in d
    assert "patients" not in d


def test_admin_doctor_detail_404():
    assert c.get("/api/admin/doctors/999999", headers=H).status_code == 404


def test_password_reset_trigger_produces_working_reset():
    _, did = _make_doctor("adm_reset@x.ru")
    r = c.post(f"/api/admin/doctors/{did}/password-reset", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["sent_to"] == "adm_reset@x.ru"
    token = body["dev_token"]        # в деве почты нет — токен возвращается
    # токен реально работает в штатном /reset
    rr = c.post("/api/auth/reset", json={"email": "adm_reset@x.ru", "token": token,
                                         "new_password": "newpass12345"})
    assert rr.status_code == 200
    # старый пароль больше не подходит, новый — подходит
    assert c.post("/api/auth/login", json={"email": "adm_reset@x.ru", "password": "pass12345", "device_id": "d"}).status_code == 401
    ok = c.post("/api/auth/login", json={"email": "adm_reset@x.ru", "password": "newpass12345", "device_id": "d"})
    assert ok.status_code == 200


def test_support_threads_show_doctor_name():
    h, did = _make_doctor("adm_support@x.ru")
    c.post("/api/support/message", json={"body": "Не приходит код входа"}, headers=h)
    threads = c.get("/api/admin/support/threads", headers=H).json()
    mine = [t for t in threads if t["doctor_id"] == did]
    assert mine and mine[0]["doctor_name"] == "Иван Тестов" and mine[0]["doctor_email"] == "adm_support@x.ru"


# ── расширенная аналитика админки ───────────────────────────────────────────
def test_insights_endpoint_shape_and_auth():
    assert c.get("/api/admin/analytics/insights").status_code == 401
    r = c.get("/api/admin/analytics/insights", headers=H).json()
    for key in ("doctors", "subscriptions", "ai", "engagement"):
        assert key in r
    d = r["doctors"]
    for key in ("total", "active_24h", "active_7d", "active_30d",
                "with_patients", "with_appointments", "demo_sessions"):
        assert key in d


def test_insights_does_not_leak_patient_data():
    r = c.get("/api/admin/analytics/insights", headers=H).json()
    blob = str(r).lower()
    for forbidden in ("last_name", "first_name", "diagnosis", "patient_name"):
        assert forbidden not in blob


def test_old_overview_still_works():
    assert c.get("/api/admin/analytics/overview", headers=H).status_code == 200
