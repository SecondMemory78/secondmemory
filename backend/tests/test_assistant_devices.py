"""Устройства голосом.

Частый урологический сценарий: «поставил Иванову стент справа», «снял катетер».
Раньше для этого надо было идти в карту. Главная осторожность — сторона: её
нельзя угадывать, перепутать бок дороже, чем переспросить.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Device, Patient

seed.run()
c = TestClient(app)


def _name():
    return c.get("/api/patients").json()[0]["last_name"]


def _say(text):
    return c.post("/api/assistant/command", json={"text": text}).json()


def _devices(pid):
    with Session(engine) as s:
        return s.exec(select(Device).where(Device.patient_id == pid)).all()


def test_стент_со_стороной_записывается():
    r = _say(f"поставил {_name()} стент справа")
    assert r["intent"] == "device" and r.get("device_id")
    with Session(engine) as s:
        d = s.get(Device, r["device_id"])
        assert d.kind == "stent" and d.side == "right" and d.active is True
    assert "справа" in r["message"]


def test_без_стороны_ассистент_переспрашивает():
    """Сторону угадывать нельзя: перепутать бок — самая дорогая ошибка здесь."""
    r = _say(f"поставил {_name()} нефростому")
    assert r["ok"] is False
    assert "слева" in r["message"] and "справа" in r["message"]


def test_катетеру_сторона_не_нужна():
    r = _say(f"поставил {_name()} катетер")
    assert r.get("device_id"), r["message"]


def test_снятие_закрывает_устройство():
    name = _name()
    pid = c.get("/api/patients").json()[0]["id"]
    before = _say(f"поставил {name} стент слева")["device_id"]
    r = _say(f"снял {name} стент слева")
    assert r.get("device_id") == before
    with Session(engine) as s:
        d = s.get(Device, before)
        assert d.active is False and d.state == "removed" and d.closed_at


def test_при_двух_подходящих_не_угадываем():
    """Закрыть не то устройство хуже, чем переспросить."""
    name = _name()
    _say(f"поставил {name} стент справа")
    _say(f"поставил {name} стент слева")
    r = _say(f"снял {name} стент")
    assert r["ok"] is False and "уточните" in r["message"].lower()


def test_нечего_снимать_говорим_прямо():
    pid = c.get("/api/patients").json()[1]["id"]
    name = c.get("/api/patients").json()[1]["last_name"]
    r = _say(f"снял {name} нефростому справа")
    assert r["ok"] is False and "нет подходящего" in r["message"]


def test_устройство_в_каталоге_меняет_данные():
    from app.services import actions as acts
    assert acts.get("device.add").level == acts.WRITES
    assert acts.get("device.close").level == acts.WRITES
