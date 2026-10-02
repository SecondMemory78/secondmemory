"""Диагноз и начало приёма голосом.

Диагноз — не то же, что заметка: неверный код выглядит в карте как факт и
уезжает в документы. Поэтому код берём только из справочника, при нескольких
подходящих не выбираем за врача, и основным диагноз сам не становится.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import PatientDiagnosis, Encounter

seed.run()
c = TestClient(app)


def _name(i=0):
    return c.get("/api/patients").json()[i]["last_name"]


def _say(text):
    return c.post("/api/assistant/command", json={"text": text}).json()


def test_диагноз_по_коду_добавляется():
    r = _say(f"поставь {_name()} диагноз N40.0")
    assert r["intent"] == "diagnosis" and r.get("diagnosis_id"), r["message"]
    with Session(engine) as s:
        d = s.get(PatientDiagnosis, r["diagnosis_id"])
        assert d.code.upper().startswith("N40")
        assert d.title, "название должно браться из справочника"


def test_основным_диагноз_сам_не_становится():
    """Основной диагноз определяет шапку карты и попадает в документы."""
    r = _say(f"поставь {_name(1)} диагноз N40.0")
    with Session(engine) as s:
        assert s.get(PatientDiagnosis, r["diagnosis_id"]).is_primary is False


def test_код_не_выдумывается():
    r = _say(f"поставь {_name()} диагноз ЗЗЗ99.9")
    assert r["ok"] is False
    assert "справочник" in r["message"].lower()
    with Session(engine) as s:
        assert not s.exec(select(PatientDiagnosis).where(
            PatientDiagnosis.code == "ЗЗЗ99.9")).first()


def test_при_нескольких_подходящих_просит_уточнить():
    r = _say(f"поставь {_name()} диагноз камень")
    if r["ok"] is False:
        assert "уточните" in r["message"].lower() or "справочник" in r["message"].lower()


def test_приём_начинается_голосом():
    r = _say(f"начни приём {_name(2)}")
    assert r["intent"] == "encounter" and r.get("encounter_id"), r["message"]
    with Session(engine) as s:
        assert s.get(Encounter, r["encounter_id"]).closed_at is None


def test_второй_приём_не_плодится():
    name = _name(2)
    _say(f"начни приём {name}")
    r = _say(f"начни приём {name}")
    assert r["ok"] is False and "уже открыт" in r["message"]


def test_новые_действия_в_каталоге():
    from app.services import actions as acts
    assert acts.get("diagnosis.add").level == acts.WRITES
    assert acts.get("encounter.start").level == acts.WRITES


# ── подтверждение диагноза ──────────────────────────────────────────────────
# Диагноз — клиническое суждение, ошибка в нём весит не меньше, чем в
# назначении. Поэтому предложенный ассистентом диагноз ждёт врача.

def test_диагноз_от_ассистента_ждёт_подтверждения():
    pid = c.get("/api/patients").json()[0]["id"]
    r = _say(f"поставь {_name()} диагноз N40")
    with Session(engine) as s:
        d = s.get(PatientDiagnosis, r["diagnosis_id"])
        assert d.confirmed is False
        assert d.source == "ai_suggested"
        assert d.confirmed_by is None
    assert "подтвердите" in r["message"].lower()


def test_неподтверждённый_не_может_стать_основным():
    pid = c.get("/api/patients").json()[0]["id"]
    did = _say(f"поставь {_name()} диагноз N21")["diagnosis_id"]
    r = c.post(f"/api/patients/{pid}/diagnoses/{did}/primary")
    assert r.status_code == 400
    assert "подтвердите" in r.json()["detail"].lower()


def test_подтверждение_запоминает_врача_и_время():
    pid = c.get("/api/patients").json()[0]["id"]
    did = _say(f"поставь {_name()} диагноз N30")["diagnosis_id"]
    assert c.post(f"/api/patients/{pid}/diagnoses/{did}/confirm").status_code == 200
    with Session(engine) as s:
        d = s.get(PatientDiagnosis, did)
        assert d.confirmed is True and d.confirmed_by == 1 and d.confirmed_at
        # происхождение не подменяется подтверждением
        assert d.source == "ai_suggested"


def test_после_подтверждения_можно_сделать_основным():
    pid = c.get("/api/patients").json()[0]["id"]
    did = _say(f"поставь {_name()} диагноз N13")["diagnosis_id"]
    c.post(f"/api/patients/{pid}/diagnoses/{did}/confirm")
    assert c.post(f"/api/patients/{pid}/diagnoses/{did}/primary").status_code == 200


def test_внесённый_врачом_подтверждён_сразу():
    """Врач вносит диагноз сам — лишнего нажатия быть не должно."""
    pid = c.get("/api/patients").json()[0]["id"]
    r = c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40", "wording": "ДГПЖ"})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(PatientDiagnosis, r.json()["id"]).confirmed is True


def test_подтверждение_отмечается_в_журнале():
    pid = c.get("/api/patients").json()[0]["id"]
    did = _say(f"поставь {_name()} диагноз N20")["diagnosis_id"]
    from app.services.ai_journal import chain, CONFIRMED
    c.post(f"/api/patients/{pid}/diagnoses/{did}/confirm")
    with Session(engine) as s:
        link = chain(s, "diagnosis", did)
        assert link and link[-1]["outcome"] == CONFIRMED
