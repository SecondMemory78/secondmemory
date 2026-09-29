"""Задача 4: разбор смешанной диктовки — сегменты, сопоставление, применение, приватность."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def _consented(last, first="Т"):
    pid = c.post("/api/patients", headers=H, json={"last_name": last, "first_name": first}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H)
    return pid


def _dict(sim, key=""):
    hh = dict(H)
    if key:
        hh["idempotency-key"] = key
    return c.post("/api/dictation", headers=hh, json={"text": "запись", "sim": sim}).json()


def test_segments_created_and_patient_autoresolved():
    pa = _consented("Диктов", "Иван")
    sim = [
        {"seg_type": "patient_note", "last_name": "Диктов", "first_name": "Иван", "content": "назначен тамсулозин"},
        {"seg_type": "call", "content": "позвонить по анализам", "when_text": "завтра"},
        {"seg_type": "idea", "content": "добавить чек-лист перед ТУР"},
    ]
    d = _dict(sim)
    assert len(d["segments"]) == 3
    note_seg = [x for x in d["segments"] if x["seg_type"] == "patient_note"][0]
    assert note_seg["status"] == "assigned" and note_seg["resolved_patient_id"] == pa   # узнан автоматически


def test_ambiguous_patient_waits_for_choice():
    # два пациента с одинаковым ФИО → сегмент неоднозначен
    _consented("Двойников", "Пётр"); _consented("Двойников", "Пётр")
    d = _dict([{"seg_type": "patient_note", "last_name": "Двойников", "first_name": "Пётр", "content": "жалобы"}])
    seg = d["segments"][0]
    assert seg["status"] == "pending" and seg["identity"]["action"] == "choose"
    # применение оставит его в pending_choice
    r = c.post(f"/api/dictation/{d['id']}/confirm", headers=H).json()
    assert seg["id"] in r["pending_choice"]


def test_confirm_applies_note_task_call_idea():
    pa = _consented("Применёв", "А")
    d = _dict([
        {"seg_type": "patient_note", "last_name": "Применёв", "first_name": "А", "content": "осмотр без особенностей"},
        {"seg_type": "task", "content": "контроль PSA", "when_text": "через 3 месяца"},
        {"seg_type": "idea", "content": "идея для сайта"},
    ])
    r = c.post(f"/api/dictation/{d['id']}/confirm", headers=H).json()
    assert len(r["applied"]) == 3
    # заметка попала в карту пациента
    notes = [n["text"] for n in c.get(f"/api/patients/{pa}/notes", headers=H).json()]
    assert "осмотр без особенностей" in notes
    # задача с датой и идея — в напоминаниях
    titles = [t["title"] for t in c.get("/api/reminders", headers=H).json()]
    assert "контроль PSA" in titles and "идея для сайта" in titles


def test_privacy_note_goes_only_to_assigned_patient():
    pa = _consented("Личнов", "А"); pb = _consented("Чужов", "Б")
    d = _dict([{"seg_type": "patient_note", "last_name": "Личнов", "first_name": "А", "content": "секрет А"}])
    c.post(f"/api/dictation/{d['id']}/confirm", headers=H)
    assert "секрет А" in [n["text"] for n in c.get(f"/api/patients/{pa}/notes", headers=H).json()]
    assert "секрет А" not in [n["text"] for n in c.get(f"/api/patients/{pb}/notes", headers=H).json()]


def test_idempotent_dictation():
    d1 = _dict([{"seg_type": "idea", "content": "раз"}], key="dic-1")
    d2 = _dict([{"seg_type": "idea", "content": "раз"}], key="dic-1")
    assert d1["id"] == d2["id"]
