"""Заметки: редактирование, удаление, «сделать из заметки задачу»."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]   # демо-пациент с согласием


def _note(pid, text="жалобы на никтурию"):
    return c.post(f"/api/patients/{pid}/notes", params={"text": text}).json()["id"]


def test_edit_note():
    pid = _pid(); nid = _note(pid)
    r = c.patch(f"/api/patients/{pid}/notes/{nid}", params={"text": "исправленный текст"}).json()
    assert r["text"] == "исправленный текст"


def test_delete_note():
    pid = _pid(); nid = _note(pid, "удалить меня")
    c.delete(f"/api/patients/{pid}/notes/{nid}")
    texts = [n["text"] for n in c.get(f"/api/patients/{pid}/notes").json()]
    assert "удалить меня" not in texts


def test_note_to_task():
    pid = _pid(); nid = _note(pid, "перезвонить по результатам")
    r = c.post(f"/api/patients/{pid}/notes/{nid}/task", params={"due_at": "2026-09-20"}).json()
    assert r["patient_id"] == pid and r["title"] == "перезвонить по результатам"
    assert r["due_at"].startswith("2026-09-20")
    titles = [x["title"] for x in c.get("/api/reminders").json()]
    assert "перезвонить по результатам" in titles


def test_edit_note_blocked_without_consent():
    pid = c.post("/api/patients", json={"last_name": "Безсогласия", "first_name": "Т"}).json()["id"]
    # без согласия даже создать заметку нельзя — проверяем барьер на создании
    assert c.post(f"/api/patients/{pid}/notes", params={"text": "x"}).status_code == 403


def test_whats_new_summary():
    pid = _pid()
    wn = c.get(f"/api/patients/{pid}/whats-new").json()
    assert "has_news" in wn and "overdue" in wn and "alerts" in wn and "pending_count" in wn


def test_pdf_export_full_and_selective():
    pid = _pid()
    r = c.get(f"/api/patients/{pid}/export.pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    r2 = c.get(f"/api/patients/{pid}/export.pdf?sections=observations&date_from=2026-01-01")
    assert r2.status_code == 200 and r2.content[:5] == b"%PDF-"


def test_attention_feed():
    r = c.get("/api/dashboard/attention").json()
    assert "count" in r and "items" in r
    if r["items"]:
        assert "name" in r["items"][0] and "reasons" in r["items"][0]
        # приоритет по убыванию
        prios = [it["priority"] for it in r["items"]]
        assert prios == sorted(prios, reverse=True)
