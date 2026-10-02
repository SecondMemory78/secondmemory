"""Сведения со слов пациента — не измерение.

Врач говорит «со слов пациента ПСА был 7,2» — это анамнез, а не лабораторный
результат. Если показывать такое рядом с настоящими значениями, через месяц
никто не вспомнит разницу, а пациент получит памятку, где его же слова
напечатаны как результат обследования.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed
from app.db import engine
from app.models import Observation
from app.services.pdf_export import handout_sections

seed.run()
c = TestClient(app)


def _name():
    return c.get("/api/patients").json()[0]["last_name"]


def test_со_слов_помечается_источником():
    r = c.post("/api/assistant/command",
               json={"text": f"со слов пациента у {_name()} ПСА был 7,2"}).json()
    with Session(engine) as s:
        o = s.get(Observation, r["observation_ids"][0])
        assert o.provenance == "patient_words"
    assert "со слов" in r["message"]


def test_обычное_измерение_не_помечается():
    r = c.post("/api/assistant/command",
               json={"text": f"у {_name()} ПСА 4,1"}).json()
    with Session(engine) as s:
        assert s.get(Observation, r["observation_ids"][0]).provenance == "ai_extracted"


def test_разные_формулировки_ловятся():
    for phrase in ("по словам пациента", "пациент говорит что", "пациент сказал"):
        r = c.post("/api/assistant/command",
                   json={"text": f"{phrase} у {_name()} креатинин 99"}).json()
        ids = r.get("observation_ids")
        if not ids:
            continue
        with Session(engine) as s:
            assert s.get(Observation, ids[0]).provenance == "patient_words", phrase


def test_в_памятку_пациенту_не_попадает():
    """Иначе пациент унесёт бумагу, где его слова напечатаны как результат."""
    base = {"prescriptions": [], "appointments": [], "devices": [], "procedures": []}
    said = [
        {"parameter_code": "psa", "label": "ПСА", "value_num": 3.0, "unit": "нг/мл",
         "effective_date": "2026-01-10", "status": "confirmed", "provenance": "patient_words"},
        {"parameter_code": "psa", "label": "ПСА", "value_num": 7.2, "unit": "нг/мл",
         "effective_date": "2026-09-01", "status": "confirmed", "provenance": "patient_words"},
    ]
    out = {x["key"]: x for x in handout_sections(dict(base, observations=said))}
    assert "changes" not in out


def test_в_выписку_не_идёт_но_врач_об_этом_знает():
    from app.models import Encounter, Patient
    from app import clock
    from datetime import timedelta
    from app.services.discharge import build_draft
    with Session(engine) as s:
        p = Patient(doctor_id=1, last_name="Словов", first_name="Иван", middle_name="")
        s.add(p); s.commit(); s.refresh(p)
        enc = Encounter(doctor_id=1, patient_id=p.id, type="visit", reason="приём",
                        started_at=clock.now() - timedelta(days=2))
        s.add(enc); s.commit(); s.refresh(enc)
        s.add(Observation(patient_id=p.id, parameter_code="psa_total", value_num=7.2,
                          unit="нг/мл", effective_date=date.today(), status="confirmed",
                          provenance="patient_words"))
        s.commit()
        built = build_draft(s, enc.id)

    assert not built["sections"].get("investigations")
    assert any("со слов" in x["why"] for x in built["excluded"]), \
        "врач не узнает, что данные есть, но не вошли"
