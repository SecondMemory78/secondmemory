"""Учёт расхода и суточные лимиты ИИ (защита от разорения на токенах)."""
import os, tempfile, io
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"x-admin-token": "dev-admin-token"}


def _fresh_token(email):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone, "password": "pass12345",
                                       "full_name": "Лимит Врач", "specialty": "Уролог"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
    h = {"Authorization": "Bearer " + v["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)   # dev-фолбэк: активирует сразу
    return h


def test_daily_ocr_limit_enforced():
    old = os.environ.get("AI_LIMIT_OCR")
    os.environ["AI_LIMIT_OCR"] = "3"                      # низкий лимит только на этот тест
    try:
        H2 = _fresh_token("limit@x.ru")                  # свежий врач: расход = 0
        pid = c.post("/api/patients", json={"last_name": "Расходов", "first_name": "И"}, headers=H2).json()["id"]
        c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H2)
        f = lambda: c.post(f"/api/patients/{pid}/documents",
                           files={"file": ("d.jpg", io.BytesIO(b"x"), "image/jpeg")}, headers=H2)
        codes = [f().status_code for _ in range(4)]
        assert codes[:3] == [200, 200, 200] and codes[3] == 429
    finally:
        if old is None: os.environ.pop("AI_LIMIT_OCR", None)
        else: os.environ["AI_LIMIT_OCR"] = old


def test_usage_today_shape():
    u = c.get("/api/usage/today").json()
    for k in ("ocr", "stt", "llm"):
        assert "used" in u[k] and "limit" in u[k] and "remaining" in u[k]


def test_admin_usage_analytics():
    assert c.get("/api/admin/usage/summary", headers=H).json()["total"] >= 1
    bd = c.get("/api/admin/usage/by-doctor", headers=H).json()
    assert isinstance(bd, list) and len(bd) >= 1 and "today" in bd[0]
    assert isinstance(c.get("/api/admin/usage/daily", headers=H).json(), list)
    assert c.get("/api/admin/usage/summary").status_code == 401     # без токена
