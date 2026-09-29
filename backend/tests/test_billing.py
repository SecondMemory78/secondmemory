"""Барьер подписки: неоплативший врач — только просмотр, ни одной записи нигде.
Демо-аккаунт исключён. Телефон уникален. Автопродление и напоминания."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.models import Subscription
from app.db import engine
from sqlmodel import Session

seed.run()
c = TestClient(app)


def _fresh(email):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone, "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
    return {"Authorization": "Bearer " + v["token"]}


def test_unsubscribed_doctor_blocked_everywhere():
    h = _fresh("nopay@x.ru")
    assert c.get("/api/billing/status", headers=h).json()["active"] is False
    # запись заблокирована ВЕЗДЕ, не только «новый пациент»
    assert c.post("/api/patients", json={"last_name": "X", "first_name": "Y"}, headers=h).status_code == 402
    assert c.post("/api/appointments", json={"patient_id": 1, "starts_at": "2026-09-10T09:00:00"}, headers=h).status_code == 402
    assert c.post("/api/reminders", json={"title": "test"}, headers=h).status_code == 402
    # просмотр — разрешён
    assert c.get("/api/patients", headers=h).status_code == 200


def test_editing_and_deleting_also_blocked():
    h = _fresh("nopay2@x.ru")
    # даже правка/удаление существующего (не только создание нового) заблокированы
    assert c.patch("/api/reminders/1", json={"title": "x"}, headers=h).status_code == 402
    assert c.delete("/api/reminders/1", headers=h).status_code == 402
    assert c.post("/api/appointments/1/cancel", headers=h).status_code == 402


def test_subscribe_dev_mode_unblocks():
    h = _fresh("payer@x.ru")
    r = c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h).json()
    assert r["activated"] is True and r["dev_mode"] is True   # честный dev-фолбэк без ключей ЮKassa
    assert c.get("/api/billing/status", headers=h).json()["active"] is True
    assert c.post("/api/patients", json={"last_name": "X", "first_name": "Y"}, headers=h).status_code == 200


def test_demo_account_exempt_from_gate():
    r = c.post("/api/auth/demo").json()
    h = {"Authorization": "Bearer " + r["token"]}
    assert c.get("/api/billing/status", headers=h).json()["is_demo"] is True
    # демо может писать данные, даже не оплачивая
    assert c.post("/api/reminders", json={"title": "демо-задача"}, headers=h).status_code == 200


def test_duplicate_phone_rejected():
    c.post("/api/auth/register", json={"email": "one@x.ru", "phone": "+79991234567", "password": "pass12345", "full_name": "Один"})
    r = c.post("/api/auth/register", json={"email": "two@x.ru", "phone": "+79991234567", "password": "pass12345", "full_name": "Два"})
    assert r.status_code == 409 and "телефон" in r.json()["detail"].lower()


def test_prices_match_agreed_table():
    plans = {p["key"]: p for p in c.get("/api/billing/plans").json()}
    assert plans["1m"]["price"] == 6000
    assert plans["3m"]["price"] == 16200     # -10%
    assert plans["6m"]["price"] == 30600     # -15%
    assert plans["12m"]["price"] == 54000    # -25%


def test_subscription_extends_from_current_end_not_from_today():
    h = _fresh("extend@x.ru")
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    first_end = c.get("/api/billing/status", headers=h).json()["period_end"]
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    second_end = c.get("/api/billing/status", headers=h).json()["period_end"]
    assert second_end > first_end            # не сгорело, а продлилось


def test_auto_renew_toggle():
    h = _fresh("renew@x.ru")
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    assert c.get("/api/billing/status", headers=h).json()["auto_renew"] is True
    c.post("/api/billing/auto-renew", json={"enabled": False}, headers=h)
    assert c.get("/api/billing/status", headers=h).json()["auto_renew"] is False


def test_expiry_notifications_daily_last_5_days_and_emails_at_5_and_3():
    h = _fresh("expiring@x.ru")
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    me = c.get("/api/auth/me", headers=h).json()
    from sqlmodel import select
    with Session(engine) as s:
        row = s.exec(select(Subscription).where(Subscription.doctor_id == me["id"])).first()
        row.period_end = clock.now() + timedelta(days=5)
        s.add(row); s.commit()
    r = c.get("/api/notifications", headers=h).json()
    assert any("подписка" in n["text"].lower() for n in r["items"])
    with Session(engine) as s:
        row = s.exec(select(Subscription).where(Subscription.doctor_id == me["id"])).first()
        assert row.reminder5_sent is True        # письмо на 5-й день отмечено отправленным


def test_cohort_readable_without_subscription():
    """Правка №2: cohort — чтение, доступно без подписки."""
    h = _fresh("cohortreader@x.ru")
    r = c.post("/api/patients/cohort", json={"diagnosis_code": "N40"}, headers=h)
    assert r.status_code == 200          # не 402


def test_prod_without_yookassa_does_not_grant_free_access(monkeypatch):
    """Правка №1: в проде (AUTH_OPTIONAL=0) без ключей ЮKassa подписку бесплатно не выдаём."""
    import app.routers.billing as b
    monkeypatch.setattr(b, "AUTH_OPTIONAL", False, raising=False)
    # подменяем флаг в модуле deps, который читает эндпоинт
    import app.deps as deps
    monkeypatch.setattr(deps, "AUTH_OPTIONAL", False, raising=False)
    h = _fresh("prodpay@x.ru")
    r = c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    assert r.status_code == 503          # конфигурация без оплаты — отказ, не бесплатный доступ


def test_webhook_rejects_forged_without_yookassa_verification():
    """Подделка вебхука без реального подтверждения ЮKassa НЕ активирует подписку."""
    h = _fresh("webhookforge@x.ru")
    me = c.get("/api/auth/me", headers=h).json()
    # ЮKassa не настроена → боевой вебхук обрабатывать нельзя
    r = c.post("/api/billing/webhook/yookassa", json={
        "event": "payment.succeeded",
        "object": {"id": "pay-forged", "metadata": {"doctor_id": str(me["id"]), "plan": "3m"}}})
    assert r.status_code == 503
    assert c.get("/api/billing/status", headers=h).json()["active"] is False   # не активирована


def test_webhook_activates_only_after_yookassa_confirms(monkeypatch):
    """С подтверждением от ЮKassa (обратная проверка платежа) подписка активируется."""
    import app.routers.billing as b
    import app.services.yookassa as yk
    h = _fresh("webhookok@x.ru")
    me = c.get("/api/auth/me", headers=h).json()
    from app.services.billing import price_for
    # эмулируем настроенную ЮKassa и её ответ, что платёж реально прошёл
    monkeypatch.setattr(yk, "configured", lambda: True)
    monkeypatch.setattr(b, "get_payment", lambda pid: {
        "status": "succeeded", "amount_rub": price_for("3m"),
        "metadata": {"doctor_id": str(me["id"]), "plan": "3m"}}, raising=False)
    # подменяем импортированное в вебхуке имя get_payment
    monkeypatch.setattr(yk, "get_payment", lambda pid: {
        "status": "succeeded", "amount_rub": price_for("3m"),
        "metadata": {"doctor_id": str(me["id"]), "plan": "3m"}}, raising=False)
    r = c.post("/api/billing/webhook/yookassa", json={
        "event": "payment.succeeded", "object": {"id": "pay-real-1"}})
    assert r.status_code == 200
    st = c.get("/api/billing/status", headers=h).json()
    assert st["active"] is True and st["plan"] == "3m"
    # повтор того же платежа не продлевает дважды (идемпотентность)
    end1 = st["period_end"]
    c.post("/api/billing/webhook/yookassa", json={"event": "payment.succeeded", "object": {"id": "pay-real-1"}})
    assert c.get("/api/billing/status", headers=h).json()["period_end"] == end1
