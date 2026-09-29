"""Центр уведомлений: генерация из просрочки/лимитов, прочтение, деперсонализация Telegram."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.services.notifications import escalation_text
from app.models import Reminder, Notification

seed.run()
c = TestClient(app)


def test_overdue_reminder_creates_notification():
    # заведём просроченную задачу напрямую
    from sqlmodel import Session
    from app.db import engine
    with Session(engine) as s:
        s.add(Reminder(doctor_id=1, title="Контроль PSA просрочен",
                       due_at=clock.now() - timedelta(days=2), status="open"))
        s.commit()
    r = c.get("/api/notifications").json()
    assert r["unread"] >= 1
    assert any("просрочен" in n["text"].lower() for n in r["items"])


def test_mark_read_reduces_unread():
    r = c.get("/api/notifications").json()
    nid = r["items"][0]["id"]
    c.post(f"/api/notifications/{nid}/read")
    assert all(n["id"] != nid or n["read"] for n in c.get("/api/notifications").json()["items"])


def test_no_duplicates_on_refresh():
    a = c.get("/api/notifications").json()["items"]
    b = c.get("/api/notifications").json()["items"]
    assert len(a) == len(b)          # повторный вызов не плодит дубли


def test_read_all():
    c.post("/api/notifications/read-all")
    assert c.get("/api/notifications").json()["unread"] == 0


def test_telegram_text_is_depersonalized():
    n = Notification(doctor_id=1, text="Просрочено: Контроль PSA у Иванова")
    assert "Иванов" not in escalation_text(n, "telegram")     # без ПДн
    assert "Иванов" in escalation_text(n, "max")              # MAX (РФ) — можно детали


def test_admin_audit_logs_actions():
    H = {"x-admin-token": "dev-admin-token"}
    # делаем админ-действие
    c.get("/api/admin/usage/summary", headers=H)
    c.get("/api/admin/analytics/overview", headers=H)
    log = c.get("/api/admin/audit", headers=H).json()
    assert isinstance(log, list) and len(log) >= 2
    actions = [r["action"] for r in log]
    assert any("usage/summary" in a for a in actions)
    assert any("analytics/overview" in a for a in actions)
    # сам просмотр журнала не логируется (нет шума)
    assert not any(a.endswith("/admin/audit") for a in actions)
    # без токена журнал недоступen
    assert c.get("/api/admin/audit").status_code == 401
