"""Задачи: перенос на конкретную дату, редактирование, удаление."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _make():
    return c.post("/api/reminders", json={"title": "Контроль PSA", "priority": 4, "project": "Входящие"}).json()["id"]


def test_reschedule_to_specific_date():
    rid = _make()
    r = c.patch(f"/api/reminders/{rid}", json={"due_at": "2026-09-15"}).json()
    assert r["due_at"].startswith("2026-09-15T09:00")


def test_edit_title_priority_section():
    rid = _make()
    r = c.patch(f"/api/reminders/{rid}", json={"title": "Контроль креатинина", "priority": 1, "project": "Контроли"}).json()
    assert r["title"] == "Контроль креатинина" and r["priority"] == 1 and r["project"] == "Контроли"


def test_clear_due_date():
    rid = _make()
    c.patch(f"/api/reminders/{rid}", json={"due_at": "2026-09-15"})
    r = c.patch(f"/api/reminders/{rid}", json={"due_at": ""}).json()
    assert r["due_at"] is None


def test_delete():
    rid = _make()
    c.delete(f"/api/reminders/{rid}")
    ids = [x["id"] for x in c.get("/api/reminders").json()]
    assert rid not in ids


def test_done_reopen_and_completed_list():
    rid = _make()
    c.post(f"/api/reminders/{rid}/done")
    # в открытых больше нет, в выполненных — есть
    assert rid not in [x["id"] for x in c.get("/api/reminders?status=open").json()]
    assert rid in [x["id"] for x in c.get("/api/reminders?status=done").json()]
    # вернуть (Отменить)
    c.post(f"/api/reminders/{rid}/reopen")
    assert rid in [x["id"] for x in c.get("/api/reminders?status=open").json()]


def test_reopen_removes_spawned_recurrence():
    r = c.post("/api/reminders", json={"title": "контроль", "repeat_days": 90,
               "due_at": "2026-09-20"}).json()
    done = c.post(f"/api/reminders/{r['id']}/done").json()
    assert done["next"] and done["next"]["id"]              # повтор создан
    nxt_id = done["next"]["id"]
    c.post(f"/api/reminders/{r['id']}/reopen")
    # авто-созданный повтор удалён (не задвоился)
    open_ids = [x["id"] for x in c.get("/api/reminders?status=open").json()]
    assert r["id"] in open_ids and nxt_id not in open_ids


def test_recurrence_units():
    from app.services.recurrence import next_due
    from datetime import datetime
    b = datetime(2026, 1, 31, 9, 0)
    assert next_due(b, "day", 1).day == 1                       # +1 день
    assert next_due(b, "day", 2).day == 2                       # через 2 дня
    assert next_due(b, "week", 1) == datetime(2026, 2, 7, 9, 0) # +неделя
    assert next_due(b, "month", 1) == datetime(2026, 2, 28, 9, 0)  # 31 янв +мес → 28 фев
    assert next_due(b, "year", 1) == datetime(2027, 1, 31, 9, 0)
    assert next_due(b, "", 1, legacy_repeat_days=90).day        # legacy работает
    assert next_due(b, "", 1) is None                            # нет повтора


def test_done_spawns_next_by_unit():
    r = c.post("/api/reminders", json={"title": "ежемесячный контроль", "due_at": "2026-03-15",
               "repeat_unit": "month", "repeat_interval": 2}).json()
    done = c.post(f"/api/reminders/{r['id']}/done").json()
    assert done["next"] and done["next"]["due_at"].startswith("2026-05-15")   # +2 месяца


def test_patch_recurrence():
    r = c.post("/api/reminders", json={"title": "t", "due_at": "2026-03-15"}).json()
    upd = c.patch(f"/api/reminders/{r['id']}", json={"repeat_unit": "week", "repeat_interval": 1}).json()
    assert upd["repeat_unit"] == "week"
