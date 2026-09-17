"""Web Push: подписка, честный фолбэк без ключей, отправка с моком, здоровье, авто-очистка."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from sqlmodel import Session, select
from app.models import PushSubscription, PushDelivery
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}
AH = {"x-admin-token": "dev-admin-token"}
SUB = {"endpoint": "https://push.example/abc", "p256dh": "keyp", "auth": "keya"}


def test_vapid_key_endpoint():
    r = c.get("/api/push/vapid-key").json()
    assert "key" in r and "configured" in r


def test_subscribe_dedup():
    c.post("/api/push/subscribe", headers=H, json=SUB)
    c.post("/api/push/subscribe", headers=H, json=SUB)      # тот же endpoint
    with Session(engine) as s:
        n = len(s.exec(select(PushSubscription).where(PushSubscription.endpoint == SUB["endpoint"])).all())
    assert n == 1                                           # дубля нет


def test_test_push_without_vapid_is_honest():
    # без VAPID-ключей отправка не выполняется, но и не падает
    r = c.post("/api/push/test", headers=H).json()
    assert r["sent"] == 0 and r["total"] >= 1


def test_send_with_mocked_webpush(monkeypatch):
    import app.services.push as push
    monkeypatch.setattr(push, "configured", lambda: True)
    monkeypatch.setattr(push, "send_to_subscription", lambda sub, payload: (True, 201, ""))
    with Session(engine) as s:
        r = push.push_to_doctor(s, 1, "task", "T", "body")
    assert r["sent"] >= 1


def test_dead_subscription_removed(monkeypatch):
    import app.services.push as push
    c.post("/api/push/subscribe", headers=H, json={"endpoint": "https://push.example/dead", "p256dh": "x", "auth": "y"})
    monkeypatch.setattr(push, "configured", lambda: True)
    monkeypatch.setattr(push, "send_to_subscription", lambda sub, payload: (False, 410, "gone"))
    me = c.get("/api/auth/me", headers=H).json()
    with Session(engine) as s:
        push.push_to_doctor(s, me["id"], "task", "T", "b")
        left = s.exec(select(PushSubscription).where(PushSubscription.endpoint == "https://push.example/dead")).all()
    assert len(left) == 0                                   # мёртвая подписка удалена


def test_admin_push_health():
    r = c.get("/api/admin/push/health", headers=AH).json()
    assert "subscriptions" in r and "by_platform" in r and "recent_errors" in r
    assert c.get("/api/admin/push/health").status_code == 401


def test_delivery_journal_written(monkeypatch):
    import app.services.push as push
    c.post("/api/push/subscribe", headers=H, json={"endpoint": "https://push.example/journal", "p256dh": "x", "auth": "y"})
    me = c.get("/api/auth/me", headers=H).json()
    monkeypatch.setattr(push, "configured", lambda: True)
    monkeypatch.setattr(push, "send_to_subscription", lambda sub, payload: (True, 201, ""))
    with Session(engine) as s:
        before = len(s.exec(select(PushDelivery)).all())
        push.push_to_doctor(s, me["id"], "digest", "T", "b")
        after = len(s.exec(select(PushDelivery)).all())
    assert after > before                                   # журнал доставки пишется


def test_admin_push_subscribe_and_test(monkeypatch):
    import app.services.push as push
    r = c.post("/api/admin/push/subscribe", headers=AH,
               json={"endpoint": "https://push.example/admin1", "p256dh": "x", "auth": "y"})
    assert r.status_code == 200
    with Session(engine) as s:
        row = s.exec(select(PushSubscription).where(PushSubscription.endpoint == "https://push.example/admin1")).first()
        assert row.is_admin_channel is True and row.doctor_id is None
    # тест-пуш админ-канала не падает без ключей
    assert c.post("/api/admin/push/test", headers=AH).status_code == 200
    # без токена — нельзя
    assert c.post("/api/admin/push/subscribe", json={"endpoint": "x", "p256dh": "x", "auth": "y"}).status_code == 401
