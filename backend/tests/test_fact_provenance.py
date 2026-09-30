"""Происхождение факта и подтверждение врачом.

ТЗ требует различать три разных вопроса, которые раньше были слиты в одно поле
status: откуда взялось значение, насколько уверена модель и подтвердил ли его
врач. Плюс кто именно подтвердил и когда.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Observation

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def test_введённое_врачом_помечено_как_своё():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/observations",
               json={"parameter_code": "psa_total", "value_num": 4.2, "unit": "нг/мл"})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        o = s.get(Observation, r.json()["id"])
        assert o.provenance == "doctor"
        assert o.machine_extracted is False


def test_подтверждение_запоминает_кто_и_когда():
    pid = _pid()
    with Session(engine) as s:
        o = Observation(patient_id=pid, parameter_code="psa_total", value_num=9.1,
                        unit="нг/мл", status="pending",
                        provenance="document", machine_extracted=True, confidence=0.82)
        s.add(o); s.commit(); oid = o.id

    assert c.post(f"/api/observations/{oid}/confirm").status_code == 200
    with Session(engine) as s:
        o = s.get(Observation, oid)
        assert o.status == "confirmed"
        assert o.confirmed_by == 1
        assert o.confirmed_at is not None
        # происхождение не подменяется подтверждением — видно, что извлекла машина
        assert o.machine_extracted is True
        assert o.provenance == "document"


def test_уверенность_модели_не_подтверждение():
    """Высокая уверенность сама по себе НЕ делает значение подтверждённым."""
    pid = _pid()
    with Session(engine) as s:
        o = Observation(patient_id=pid, parameter_code="creatinine", value_num=110,
                        unit="мкмоль/л", status="pending", machine_extracted=True,
                        confidence=0.99)
        s.add(o); s.commit()
        assert o.status == "pending"
        assert o.confirmed_by is None
