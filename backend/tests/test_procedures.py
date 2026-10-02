"""Операции и процедуры.

Их не было как сущности: операция терялась в заметках, выписку собрать было
не из чего, а на вопрос «какая последняя операция» система отвечала отказом.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed, clock
from app.db import engine
from app.models import Procedure, Device
from app.deps import set_current_doctor_id
from app.services.query import ask
from app.services.pdf_export import handout_sections

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def _add(pid, **kw):
    body = {"name": "ТУР простаты", "performed_at": str(date.today() - timedelta(days=10))}
    body.update(kw)
    return c.post(f"/api/patients/{pid}/procedures", json=body)


def test_операция_записывается():
    r = _add(_pid(), name="Стентирование мочеточника", side="right")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["side_label"] == "справа"
    assert "справа" in d["title"]


def test_сторона_не_угадывается():
    assert _add(_pid(), side="вверх").status_code == 400


def test_дата_в_будущем_отклоняется():
    future = str(date.today() + timedelta(days=3))
    assert _add(_pid(), performed_at=future).status_code == 400


def test_последняя_операция_сверху():
    pid = _pid()
    _add(pid, name="Давняя", performed_at=str(date.today() - timedelta(days=200)))
    _add(pid, name="Свежая", performed_at=str(date.today() - timedelta(days=1)))
    items = c.get(f"/api/patients/{pid}/procedures").json()["items"]
    assert items[0]["name"] == "Свежая"


def test_устройство_привязывается_только_своё():
    pid = _pid()
    with Session(engine) as s:
        other = s.exec(select(Device)).first()
    r = _add(pid, device_id=999999)
    assert r.status_code == 400


def test_мягкое_удаление_сохраняет_запись():
    pid = _pid()
    proc = _add(pid, name="Ошибочная").json()
    assert c.post(f"/api/patients/{pid}/procedures/{proc['id']}/remove").status_code == 200
    with Session(engine) as s:
        p = s.get(Procedure, proc["id"])
        assert p is not None and p.status == "cancelled"


def test_вопрос_про_операции_теперь_отвечается():
    """Раньше система говорила, что операции не ведутся."""
    pid = _pid()
    _add(pid, name="Нефрэктомия", performed_at=str(date.today() - timedelta(days=5)))
    set_current_doctor_id(1)
    with Session(engine) as s:
        r = ask(s, "Кого оперировали?")
    assert r["ok"] is True
    assert any(i["patient_id"] == pid for i in r["items"])
    assert "операция" in " ".join(i["why"] for i in r["items"]).lower()


def test_операции_в_памятке_только_подтверждённые():
    base = {"observations": [], "prescriptions": [], "appointments": [], "devices": []}
    s1 = {x["key"]: x for x in handout_sections(dict(base, procedures=[
        {"name": "ТУР простаты", "title": "ТУР простаты", "performed_at": "2026-09-01",
         "status": "done", "confirmed": True}]))}
    assert "procedures" in s1

    s2 = {x["key"]: x for x in handout_sections(dict(base, procedures=[
        {"name": "Предложено ИИ", "performed_at": "2026-09-01",
         "status": "done", "confirmed": False}]))}
    assert "procedures" not in s2


def test_отменённая_операция_в_памятку_не_идёт():
    base = {"observations": [], "prescriptions": [], "appointments": [], "devices": []}
    out = {x["key"]: x for x in handout_sections(dict(base, procedures=[
        {"name": "Отменена", "performed_at": "2026-09-01", "status": "cancelled",
         "confirmed": True}]))}
    assert "procedures" not in out
