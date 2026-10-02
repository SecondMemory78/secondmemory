"""Превращения заметки: в задачу, в карту пациента, в разбор ассистента.

Мост между «подумал» и «сделал» — то, чего нет ни в одном блокноте. Но
превращение всегда осознанное: само ничего не уезжает ни в задачи, ни в карту.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import DoctorNote, Note, Reminder

seed.run()
c = TestClient(app)


def _note(**kw):
    body = {"title": "Дела", "text": "текст",
            "checklist": [{"text": "заказать стенты", "done": False}]}
    body.update(kw)
    return c.post("/api/notes/my", json=body).json()


def test_пункт_превращается_в_задачу():
    n = _note()
    r = c.post(f"/api/notes/my/{n['id']}/checklist/to-task",
               json={"index": 0, "due_at": "2026-10-20T10:00:00"})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        task = s.get(Reminder, r.json()["reminder_id"])
        assert task.title == "заказать стенты" and task.due_at is not None


def test_пункт_остаётся_в_заметке_со_ссылкой():
    """Иначе врач увидит его снова и заведёт задачу второй раз."""
    n = _note()
    r = c.post(f"/api/notes/my/{n['id']}/checklist/to-task", json={"index": 0})
    item = r.json()["note"]["checklist"][0]
    assert item["text"] == "заказать стенты"
    assert item["reminder_id"] == r.json()["reminder_id"]


def test_повторное_превращение_отклоняется():
    n = _note()
    c.post(f"/api/notes/my/{n['id']}/checklist/to-task", json={"index": 0})
    r = c.post(f"/api/notes/my/{n['id']}/checklist/to-task", json={"index": 0})
    assert r.status_code == 409


def test_пустой_пункт_не_становится_задачей():
    n = _note(checklist=[{"text": "   ", "done": False}])
    assert c.post(f"/api/notes/my/{n['id']}/checklist/to-task",
                  json={"index": 0}).status_code == 400


def test_заметка_переносится_в_карту():
    pid = c.get("/api/patients").json()[0]["id"]
    n = _note(title="Про Иванова", text="обсудить тактику")
    r = c.post(f"/api/notes/my/{n['id']}/to-patient", json={"patient_id": pid})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        notes = s.exec(select(Note).where(Note.patient_id == pid)).all()
        assert any("обсудить тактику" in (x.text or "") for x in notes)
        # и видно, что заметка уже перенесена
        assert s.get(DoctorNote, n["id"]).patient_id == pid


def test_список_переносится_вместе_с_галочками():
    pid = c.get("/api/patients").json()[0]["id"]
    n = _note(checklist=[{"text": "сдать ПСА", "done": True},
                         {"text": "записать на приём", "done": False}])
    c.post(f"/api/notes/my/{n['id']}/to-patient", json={"patient_id": pid})
    with Session(engine) as s:
        txt = s.exec(select(Note).where(Note.patient_id == pid)).all()[-1].text
        assert "[x] сдать ПСА" in txt and "[ ] записать на приём" in txt


def test_чужому_пациенту_перенести_нельзя():
    n = _note()
    assert c.post(f"/api/notes/my/{n['id']}/to-patient",
                  json={"patient_id": 999999}).status_code == 404


def test_разбор_ассистентом_даёт_предложение():
    """Назначения и показатели из заметки идут тем же путём, что голос."""
    name = c.get("/api/patients").json()[0]["last_name"]
    n = _note(text=f"у {name} ПСА 6,4")
    r = c.post(f"/api/notes/my/{n['id']}/to-assistant")
    assert r.status_code == 200, r.text
    assert r.json().get("intent") in ("observation", "unknown", "patient_note")


def test_пустую_заметку_разбирать_нечего():
    n = _note(text="", title="Только список")
    assert c.post(f"/api/notes/my/{n['id']}/to-assistant").status_code == 400
