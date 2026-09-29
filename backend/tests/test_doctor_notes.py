"""Заметки врача: «Мои заметки» (личные, CRUD) и сквозной список заметок
по всем своим пациентам (только чтение, с изоляцией по врачу)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _doctor(email):
    phone = "+7900" + str(abs(hash(email)) % 10**7).zfill(7)
    c.post("/api/auth/register", json={"email": email, "phone": phone,
                                       "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
    h = {"Authorization": "Bearer " + v["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=h)
    return h


def test_create_list_update_delete_my_note():
    n = c.post("/api/notes/my", json={"text": "позвонить в лабораторию"}).json()
    assert n["id"] and n["text"] == "позвонить в лабораторию"
    items = c.get("/api/notes/my").json()["items"]
    assert any(x["id"] == n["id"] for x in items)
    upd = c.patch(f"/api/notes/my/{n['id']}", json={"text": "исправлено"}).json()
    assert upd["text"] == "исправлено"
    assert c.delete(f"/api/notes/my/{n['id']}").json()["ok"] is True
    assert not any(x["id"] == n["id"] for x in c.get("/api/notes/my").json()["items"])


def test_empty_note_rejected():
    assert c.post("/api/notes/my", json={"text": "   "}).status_code == 400


def test_pinned_notes_come_first():
    a = c.post("/api/notes/my", json={"text": "обычная"}).json()
    b = c.post("/api/notes/my", json={"text": "важная"}).json()
    c.post(f"/api/notes/my/{b['id']}/pin")
    items = c.get("/api/notes/my").json()["items"]
    assert items[0]["id"] == b["id"] and items[0]["pinned"] is True
    c.delete(f"/api/notes/my/{a['id']}"); c.delete(f"/api/notes/my/{b['id']}")


def test_search_my_notes():
    n = c.post("/api/notes/my", json={"text": "заказать катетеры Фолея"}).json()
    found = c.get("/api/notes/my", params={"q": "фолея"}).json()["items"]
    assert any(x["id"] == n["id"] for x in found)
    assert not any(x["id"] == n["id"] for x in c.get("/api/notes/my", params={"q": "небывалое"}).json()["items"])
    c.delete(f"/api/notes/my/{n['id']}")


def test_my_notes_isolated_between_doctors():
    hb = _doctor("notes_other@x.ru")
    mine = c.post("/api/notes/my", json={"text": "моя личная"}).json()
    other_items = c.get("/api/notes/my", headers=hb).json()["items"]
    assert not any(x["id"] == mine["id"] for x in other_items)
    # и чужую нельзя тронуть
    assert c.patch(f"/api/notes/my/{mine['id']}", json={"text": "взлом"}, headers=hb).status_code == 404
    assert c.delete(f"/api/notes/my/{mine['id']}", headers=hb).status_code == 404
    c.delete(f"/api/notes/my/{mine['id']}")


def test_all_notes_feed_spans_patients_and_is_isolated():
    pid = c.post("/api/patients", json={"last_name": "Заметкин", "first_name": "Иван"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы на никтурию"})
    items = c.get("/api/notes/all").json()["items"]
    mine = [x for x in items if x["patient_id"] == pid]
    assert mine and mine[0]["patient_name"].startswith("Заметкин")
    # другой врач этого не видит
    hb = _doctor("notes_feed_other@x.ru")
    assert not any(x["patient_id"] == pid for x in c.get("/api/notes/all", headers=hb).json()["items"])


def test_all_notes_search_by_text_and_patient():
    pid = c.post("/api/patients", json={"last_name": "Поисков", "first_name": "Пётр"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    c.post(f"/api/patients/{pid}/notes", params={"text": "контроль ПСА через месяц"})
    assert any(x["patient_id"] == pid for x in c.get("/api/notes/all", params={"q": "поисков"}).json()["items"])
    assert any(x["patient_id"] == pid for x in c.get("/api/notes/all", params={"q": "контроль пса"}).json()["items"])


# ── задачи в календаре: выборка по диапазону дат ─────────────────────────────
def test_reminders_range_filters_by_due_date():
    c.post("/api/reminders", json={"title": "в диапазоне", "due_at": "2026-07-15T10:00:00", "kind": "task"})
    c.post("/api/reminders", json={"title": "вне диапазона", "due_at": "2026-09-01T10:00:00", "kind": "task"})
    c.post("/api/reminders", json={"title": "без срока", "kind": "task"})
    rows = c.get("/api/reminders/range", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    titles = [r["title"] for r in rows]
    assert "в диапазоне" in titles
    assert "вне диапазона" not in titles
    assert "без срока" not in titles          # без due_at в календаре не место
    row = [r for r in rows if r["title"] == "в диапазоне"][0]
    assert row["day"] == "2026-07-15" and row["time"] == "10:00"


def test_reminders_range_excludes_done_and_other_doctors():
    r = c.post("/api/reminders", json={"title": "закрыть", "due_at": "2026-07-20T09:00:00"}).json()
    c.post(f"/api/reminders/{r['id']}/done")
    rows = c.get("/api/reminders/range", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    assert "закрыть" not in [x["title"] for x in rows]
    hb = _doctor("cal_range_other@x.ru")
    assert not any(x["title"] == "в диапазоне"
                   for x in c.get("/api/reminders/range", headers=hb,
                                  params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json())


# ── мягкое удаление и «Отменить» ─────────────────────────────────────────────
def test_deleted_note_is_hidden_but_restorable():
    n = c.post("/api/notes/my", json={"text": "вернуть меня"}).json()
    c.delete(f"/api/notes/my/{n['id']}")
    assert not any(x["id"] == n["id"] for x in c.get("/api/notes/my").json()["items"])
    back = c.post(f"/api/notes/my/{n['id']}/restore").json()
    assert back["id"] == n["id"] and back["text"] == "вернуть меня"
    assert any(x["id"] == n["id"] for x in c.get("/api/notes/my").json()["items"])
    c.delete(f"/api/notes/my/{n['id']}")


def test_deleted_note_cannot_be_edited_until_restored():
    n = c.post("/api/notes/my", json={"text": "удалена"}).json()
    c.delete(f"/api/notes/my/{n['id']}")
    assert c.patch(f"/api/notes/my/{n['id']}", json={"text": "правка"}).status_code == 404
    c.post(f"/api/notes/my/{n['id']}/restore")
    assert c.patch(f"/api/notes/my/{n['id']}", json={"text": "правка"}).status_code == 200
    c.delete(f"/api/notes/my/{n['id']}")


def test_foreign_note_restore_is_404():
    n = c.post("/api/notes/my", json={"text": "чужая"}).json()
    c.delete(f"/api/notes/my/{n['id']}")
    hb = _doctor("undo_other@x.ru")
    assert c.post(f"/api/notes/my/{n['id']}/restore", headers=hb).status_code == 404


def test_deleted_task_is_hidden_but_restorable():
    r = c.post("/api/reminders", json={"title": "вернуть задачу"}).json()
    c.delete(f"/api/reminders/{r['id']}")
    assert not any(x["id"] == r["id"] for x in c.get("/api/reminders").json())
    back = c.post(f"/api/reminders/{r['id']}/restore").json()
    assert back["id"] == r["id"] and back["status"] == "open"
    assert any(x["id"] == r["id"] for x in c.get("/api/reminders").json())


def test_restoring_a_live_task_is_404():
    r = c.post("/api/reminders", json={"title": "живая"}).json()
    assert c.post(f"/api/reminders/{r['id']}/restore").status_code == 404
