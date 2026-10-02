"""Утренняя сводка.

Раньше дайджест был одной строкой со счётчиком «требуют внимания трое»: врач
читал её и всё равно шёл разбираться, кто именно, а про сам день сводка не
говорила ничего — ни сколько приёмов, ни во сколько первый.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed, clock
from app.db import engine
from app.models import Appointment, Patient, Reminder

seed.run()
c = TestClient(app)


def _digest():
    r = c.get("/api/dashboard/digest")
    assert r.status_code == 200, r.text
    return r.json()


def test_сводка_говорит_о_дне_а_не_только_о_счётчике():
    d = _digest()
    assert "приём" in d["text"].lower() or "приёмов" in d["text"].lower()
    assert d["date"]


def test_в_расписании_есть_время_и_имя():
    d = _digest()
    if d["schedule"]:
        a = d["schedule"][0]
        assert a["time"] and a["name"] and a["patient_id"]
        assert a["kind"] in ("первичный", "повторный")


def test_первый_приём_назван_в_тексте():
    """Врач читает сводку с заблокированного экрана — время должно быть сразу."""
    d = _digest()
    upcoming = [a for a in d["schedule"] if not a["past"]]
    if upcoming:
        assert upcoming[0]["time"] in d["text"]


def test_отменённый_приём_в_сводку_не_идёт():
    pid = c.get("/api/patients").json()[0]["id"]
    with Session(engine) as s:
        s.add(Appointment(doctor_id=1, patient_id=pid, kind="repeat", reason="отменён",
                          starts_at=clock.now() + timedelta(hours=2), status="cancelled"))
        s.commit()
    assert not any(a["reason"] == "отменён" for a in _digest()["schedule"])


def test_просроченное_с_давностью():
    pid = c.get("/api/patients").json()[0]["id"]
    with Session(engine) as s:
        s.add(Reminder(doctor_id=1, patient_id=pid, title="Позвонить в лабораторию",
                       status="open", due_at=clock.now() - timedelta(days=5)))
        s.commit()
    d = _digest()
    item = [r for r in d["overdue"] if r["title"] == "Позвонить в лабораторию"]
    assert item and item[0]["days"] >= 5
    assert d["overdue"][0]["days"] >= item[0]["days"]      # самое давнее первым


def test_внимание_с_причиной_а_не_числом():
    d = _digest()
    if d["needs_attention"]:
        assert d["needs_attention"][0]["why"], "причина не указана"
        assert d["needs_attention"][0]["patient_id"]


def test_спокойный_день_так_и_называется():
    """Пустая сводка не должна выглядеть как сломанная."""
    from app.services.digest import _text
    assert "спокойный" in _text([], [], 0).lower()


def test_предложения_с_заглавной():
    from app.services.digest import _text
    t = _text([{"time": "09:30", "past": False}], [{"days": 2}], 3)
    for sentence in [x.strip() for x in t.split(".") if x.strip()]:
        assert sentence[0].isupper(), f"предложение с маленькой буквы: {sentence}"
