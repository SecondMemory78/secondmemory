"""Security-заход №2: хеш токена сессии, production-guard, CORS из env, уведомление поддержки."""
import os, tempfile, importlib
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from sqlmodel import Session
seed.run()
c = TestClient(app)


def test_session_token_stored_hashed_not_plaintext():
    r = c.post("/api/auth/demo").json()
    raw = r["token"]
    # сырой токен работает
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"}).status_code == 200
    # в БД лежит НЕ сырой токен, а его хеш
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("select token_hash from authsession").fetchall()
    assert all(raw != row[0] for row in rows)          # сырого токена в базе нет
    assert all(len(row[0]) == 64 for row in rows)      # это sha256-хеш (64 hex)


def test_logout_invalidates_session():
    r = c.post("/api/auth/demo").json()
    h = {"Authorization": f"Bearer {r['token']}"}
    assert c.get("/api/auth/me", headers=h).status_code == 200
    c.post("/api/auth/logout", headers=h)
    assert c.get("/api/auth/me", headers=h).status_code == 401


def test_production_guard_detects_default_secrets(monkeypatch):
    from app.main import verify_prod_config
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    monkeypatch.delenv("FIELD_KEY", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("BLIND_INDEX_KEY", raising=False)
    problems = verify_prod_config()
    assert any("ADMIN_TOKEN" in p for p in problems)
    assert any("FIELD_KEY" in p for p in problems)
    assert any("CORS" in p for p in problems)
    monkeypatch.setenv("ADMIN_TOKEN", "supersecret")
    monkeypatch.setenv("FIELD_KEY", "somekey")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.ru")
    monkeypatch.setenv("BLIND_INDEX_KEY", "indexkey")
    assert verify_prod_config() == []


def test_support_message_still_works_without_smtp():
    # без SUPPORT_EMAIL/SMTP уведомление тихо пропускается, обращение сохраняется
    r = c.post("/api/support/message", json={"body": "не работает распознавание"})
    assert r.status_code == 200
    assert any("распознавание" in m["body"] for m in r.json()["messages"])


def test_encryption_key_self_check(monkeypatch):
    """Отпечаток ключа: первый старт записывает, совпадающий — ok, другой ключ — mismatch."""
    from app.main import verify_encryption_key
    # первый вызов на свежей БД уже прошёл при seed.run() выше в модуле → сейчас должно быть ok
    assert verify_encryption_key() in ("ok", "first")
    # подменим ключ на другой → mismatch
    import app.crypto as crypto
    monkeypatch.setattr(crypto, "_key", lambda: __import__("base64").urlsafe_b64encode(b"x" * 32))
    assert verify_encryption_key() == "mismatch"


def test_rls_noop_on_sqlite_does_not_break():
    """На SQLite RLS — полный no-op: приложение работает как обычно."""
    from app.services.rls import apply_rls, set_session_scope, is_postgres
    from app.db import engine
    assert is_postgres(engine) is False       # тесты на sqlite
    apply_rls(engine)                         # не должно падать (no-op)
    # обычная работа не нарушена
    r = c.post("/api/auth/demo").json()
    h = {"Authorization": "Bearer " + r["token"]}
    assert c.get("/api/patients", headers=h).status_code == 200


def test_upload_size_limit(monkeypatch):
    """Слишком большой файл отбивается (413), а не роняет сервер по памяти."""
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")     # лимит 1 МБ для теста
    import io
    r = c.post("/api/auth/demo").json()
    h = {"Authorization": "Bearer " + r["token"]}
    pid = c.get("/api/patients", headers=h).json()[0]["id"]
    big = io.BytesIO(b"x" * (2 * 1024 * 1024))   # 2 МБ
    resp = c.post(f"/api/patients/{pid}/documents", headers=h,
                  files={"file": ("big.jpg", big, "image/jpeg")})
    assert resp.status_code == 413


def test_api_rate_limit(monkeypatch):
    """Флуд запросами отбивается 429 (защита от зацикленного фронта/атаки)."""
    from app.services import ratelimit
    r = c.post("/api/auth/demo").json()          # токен берём до понижения лимита
    h = {"Authorization": "Bearer " + r["token"]}
    monkeypatch.setenv("API_RATE_MAX", "5")
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    ratelimit._hits.clear()                       # чистый счётчик для детерминизма
    codes = [c.get("/api/patients", headers=h).status_code for _ in range(8)]
    assert 429 in codes                          # после серии запросов — лимит
    ratelimit._hits.clear()
    assert c.get("/api/health").status_code == 200   # здоровье — без лимита
