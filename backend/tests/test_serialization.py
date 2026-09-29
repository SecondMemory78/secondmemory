"""T2. Регрессия на баг: model_dump() у 'протухшего' (expired) объекта → {}.
Красный до появления app/serialization.dump."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from sqlmodel import Session
from app.db import engine, init_db
from app.models import Trigger


def test_dump_survives_expiry():
    from app.serialization import dump
    init_db()
    with Session(engine) as s:
        t = Trigger(doctor_id=1, name="x", parameter_code="psa_total", op=">", threshold=4.0)
        s.add(t); s.commit()          # commit → объект expired, model_dump() вернул бы {}
        d = dump(t)
        assert d["name"] == "x" and d["parameter_code"] == "psa_total" and d["op"] == ">"
