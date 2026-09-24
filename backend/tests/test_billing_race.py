"""Гонка вебхука ЮKassa: параллельные вебхуки с одним payment_id не должны
создавать несколько подписок (защита уникальным индексом payment_id)."""
import os, threading
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from app.models import Doctor, Subscription
from app.services.billing import price_for
import app.services.yookassa as YK
from sqlmodel import Session, select

seed.run()
c = TestClient(app)


def _doctor():
    with Session(engine) as s:
        d = Doctor(full_name="R", email=f"race{os.urandom(3).hex()}@x.ru",
                   phone="+79001234567", password_hash="x")
        s.add(d); s.commit(); s.refresh(d)
        return d.id


def test_concurrent_webhooks_single_subscription(monkeypatch):
    did = _doctor()
    pay_id = "PAY-RACE-" + os.urandom(3).hex()
    monkeypatch.setattr(YK, "configured", lambda: True)
    monkeypatch.setattr(YK, "get_payment", lambda pid: {
        "status": "succeeded", "amount_rub": price_for("1m"),
        "metadata": {"doctor_id": str(did), "plan": "1m"}})
    payload = {"event": "payment.succeeded", "object": {"id": pay_id}}

    results = []
    def hit():
        try:
            results.append(c.post("/api/billing/webhook/yookassa", json=payload).status_code)
        except Exception:
            results.append("ERR")
    ts = [threading.Thread(target=hit) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]

    assert all(r == 200 for r in results), results
    with Session(engine) as s:
        subs = s.exec(select(Subscription).where(Subscription.payment_id == pay_id)).all()
    assert len(subs) == 1, f"гонка: создано {len(subs)} подписок по одному платежу"
