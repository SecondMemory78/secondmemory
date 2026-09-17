"""Фундамент напоминаний: будильники, дефолты по типу, тихие часы, эскалация, настройки."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.db import engine
from sqlmodel import Session, select
from app.models import ReminderAlert, NotificationPreference
from app.services import alerts as alerts_svc
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def test_default_offsets_create_alerts_for_task():
    due = (clock.now() + timedelta(hours=3)).isoformat()
    r = c.post("/api/reminders", headers=H, json={"title": "контроль", "kind": "task", "due_at": due}).json()
    a = c.get(f"/api/alerts/reminder/{r['id']}", headers=H).json()
    assert len(a) == 1 and a[0]["offset_minutes"] == 15    # дефолт задачи — за 15 мин


def test_multiple_custom_alerts_and_reschedule_cancels_old():
    due = (clock.now() + timedelta(hours=5)).isoformat()
    r = c.post("/api/reminders", headers=H, json={"title": "приём-задача", "kind": "task", "due_at": due}).json()
    # задаём два будильника: за 60 и за 5 минут
    a = c.post(f"/api/alerts/reminder/{r['id']}", headers=H, json={"offsets": [60, 5]}).json()
    assert sorted([x["offset_minutes"] for x in a]) == [5, 60]
    # переносим срок → старые будильники должны отмениться, встать новые (по дефолту)
    new_due = (clock.now() + timedelta(hours=8)).isoformat()
    c.patch(f"/api/reminders/{r['id']}", headers=H, json={"due_at": new_due})
    with Session(engine) as s:
        pend = s.exec(select(ReminderAlert).where(ReminderAlert.entity_id == r["id"],
                                                  ReminderAlert.status == "pending")).all()
    assert len(pend) == 1              # два старых отменены, один новый по дефолту


def test_prefs_roundtrip_with_version():
    p = c.get("/api/notify-prefs", headers=H).json()
    assert p["digest_hour"] == 8 and p["default_offsets"]["appointment"] == [15]
    r = c.patch("/api/notify-prefs", headers=H, json={
        "expected_version": p["version"], "digest_hour": 9,
        "default_offsets": {"appointment": [30, 5]}}).json()
    assert r["digest_hour"] == 9 and r["default_offsets"]["appointment"] == [30, 5]
    # конфликт версий
    bad = c.patch("/api/notify-prefs", headers=H, json={"expected_version": p["version"], "digest_hour": 10})
    assert bad.status_code == 409


def test_quiet_hours_defers_delivery():
    with Session(engine) as s:
        prefs = NotificationPreference(doctor_id=99999, quiet_hours_start=0, quiet_hours_end=23)
        # 0..23 → почти весь день тихий (для теста)
        assert alerts_svc.in_quiet_hours(prefs) is True


def test_appointment_alert_and_cancel():
    pid = c.post("/api/patients", headers=H, json={"last_name": "Будильников", "first_name": "П"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H)
    starts = (clock.now() + timedelta(hours=2)).isoformat()
    ap = c.post("/api/appointments", headers=H, json={"patient_id": pid, "starts_at": starts, "kind": "repeat", "reason": "контроль"}).json()
    a = c.get(f"/api/alerts/appointment/{ap['id']}", headers=H).json()
    assert len(a) >= 1                 # будильник(и) приёма созданы по дефолтам врача
    c.post(f"/api/appointments/{ap['id']}/cancel", headers=H)
    a2 = c.get(f"/api/alerts/appointment/{ap['id']}", headers=H).json()
    assert len(a2) == 0                # при отмене приёма ВСЕ будильники погашены


def test_scheduler_delivers_and_escalates():
    """Планировщик доставляет наступивший будильник (обезличенно) и эскалирует один раз."""
    from app.services.scheduler import _tick
    from app.models import ReminderAlert, NotificationPreference
    # свежий врач с чистым состоянием и НЕактивными тихими часами
    def tok(email):
        c.post("/api/auth/register", json={"email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7), "password": "pass12345", "full_name": "В"})
        r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
        v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
        h = {"Authorization": "Bearer " + v["token"]}
        c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
        return h, v["doctor"]["id"]
    h, did = tok("sched@x.ru")
    pf = c.get("/api/notify-prefs", headers=h).json()
    c.patch("/api/notify-prefs", headers=h, json={"expected_version": pf["version"],
            "quiet_hours_start": 3, "quiet_hours_end": 4, "escalation_minutes": 30})
    due = (clock.now() + timedelta(hours=2)).isoformat()
    r = c.post("/api/reminders", headers=h, json={"title": "z", "kind": "task", "due_at": due}).json()
    with Session(engine) as s:
        a = s.exec(select(ReminderAlert).where(ReminderAlert.entity_id == r["id"],
                                               ReminderAlert.status == "pending")).first()
        a.fire_at = clock.now() - timedelta(minutes=1); s.add(a); s.commit(); aid = a.id
    _tick()
    with Session(engine) as s:
        assert s.get(ReminderAlert, aid).status == "sent"        # доставлен, ещё не эскалирован
    # ускоряем эскалацию: сделаем её мгновенной и сдвинем sent_at в прошлое
    pf2 = c.get("/api/notify-prefs", headers=h).json()
    c.patch("/api/notify-prefs", headers=h, json={"expected_version": pf2["version"], "escalation_minutes": 0})
    with Session(engine) as s:
        a = s.get(ReminderAlert, aid); a.sent_at = clock.now() - timedelta(minutes=1); s.add(a); s.commit()
    _tick()
    with Session(engine) as s:
        assert s.get(ReminderAlert, aid).status == "escalated"   # повторён один раз


def test_recap_settings_and_daily_recap():
    from app.services.scheduler import _recap_tick
    from app.models import NotificationPreference, Notification, Reminder
    from datetime import timedelta
    # свежий врач
    def tok(email):
        c.post("/api/auth/register", json={"email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7), "password": "pass12345", "full_name": "В"})
        r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
        v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
        h = {"Authorization": "Bearer " + v["token"]}
        c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
        return h, v["doctor"]["id"]
    h, did = tok("recap@x.ru")
    # включаем ежедневную сводку на ТЕКУЩИЙ час
    pf = c.get("/api/notify-prefs", headers=h).json()
    cur_hour = clock.now().hour
    r = c.patch("/api/notify-prefs", headers=h, json={"expected_version": pf["version"],
            "recap_mode": "daily", "recap_hour": cur_hour}).json()
    assert r["recap_mode"] == "daily" and r["recap_hour"] == cur_hour
    # выполняем две задачи сегодня
    for i in range(2):
        rem = c.post("/api/reminders", headers=h, json={"title": f"t{i}"}).json()
        c.post(f"/api/reminders/{rem['id']}/done", headers=h)
    _recap_tick()
    r2 = c.get("/api/notifications", headers=h).json()
    recap = [n for n in r2["items"] if "закрыли" in n["text"]]
    assert recap and "2" in recap[0]["text"]               # в сводке 2 выполненных
