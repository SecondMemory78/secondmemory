"""Разрешение личности пациента — правила PAT и приёмка A01–A04."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(
    TestClient(app).post("/api/auth/demo").content)["token"]}


def _mk(last, first, dob, mid="", sex=""):
    return c.post("/api/patients",
                  json={"last_name": last, "first_name": first, "middle_name": mid,
                        "birth_date": dob, "sex": sex}, headers=H)


def test_A01_exact_repeat_uses_same_card():
    _mk("Тестов", "Иван", "2002-08-15", "Иванович")
    r = c.post("/api/patients/check-identity", params={"mode": "auto"},
               json={"last_name": "Тестов", "first_name": "Иван", "middle_name": "Иванович",
                     "birth_date": "2002-08-15"}, headers=H).json()
    assert r["action"] == "use"


def test_A02_same_name_diff_dob_is_different_person():
    _mk("Разныхдат", "Иван", "2002-08-15")
    r = c.post("/api/patients/check-identity", params={"mode": "auto"},
               json={"last_name": "Разныхдат", "first_name": "Иван", "birth_date": "2002-08-16"}, headers=H).json()
    assert r["action"] == "similar" and r["reason"] == "name_match_dob_differs"


def test_A03_two_identical_cards_ask_choose():
    _mk("Двойников", "Пётр", "1980-03-02")
    _mk("Двойников", "Пётр", "1980-03-02")
    r = c.post("/api/patients/check-identity", params={"mode": "auto"},
               json={"last_name": "Двойников", "first_name": "Пётр", "birth_date": "1980-03-02"}, headers=H).json()
    assert r["action"] == "choose" and len(r["candidates"]) >= 2


def test_A04_external_id_conflicts_with_dob():
    p = _mk("Внешниев", "Олег", "1975-05-05").json()
    # привяжем внешний ID
    import app.models as m
    from app.db import engine
    from sqlmodel import Session
    with Session(engine) as s:
        s.add(m.PatientExternalId(patient_id=p["id"], system="ЕМИАС", value="X-100")); s.commit()
    r = c.post("/api/patients/check-identity", params={"mode": "auto"},
               json={"last_name": "Внешниев", "first_name": "Олег", "birth_date": "1999-09-09",
                     "external_system": "ЕМИАС", "external_value": "X-100"}, headers=H).json()
    assert r["action"] == "conflict"


def test_manual_create_warns_via_check_but_allows():
    _mk("Похожев", "Семён", "1990-01-01")
    # фронт сперва спрашивает check-identity — получает предупреждение о похожем
    warn = c.post("/api/patients/check-identity", params={"mode": "manual"},
                  json={"last_name": "Похожев", "first_name": "Семён", "birth_date": "1990-01-02"}, headers=H).json()
    assert warn["action"] in ("similar", "choose")
    # но создать всё равно можно — create не блокирует
    ok = c.post("/api/patients",
                json={"last_name": "Похожев", "first_name": "Семён", "birth_date": "1990-01-02"}, headers=H)
    assert ok.status_code == 200 and "id" in ok.json()


def test_merge_moves_data_and_hides_card():
    a = _mk("Слияньев", "Артём", "1988-08-08").json()
    b = _mk("Слияньев", "Артём", "1988-08-08").json()
    c.post(f"/api/patients/{b['id']}/consent/electronic", json={"agreed": True}, headers=H)
    c.post(f"/api/patients/{b['id']}/notes", params={"text": "заметка на дубле"}, headers=H)
    r = c.post("/api/patients/merge", json={"keep_id": a["id"], "merge_id": b["id"]}, headers=H).json()
    assert r["ok"] is True
    ids = [p["id"] for p in c.get("/api/patients", headers=H).json()]
    assert b["id"] not in ids and a["id"] in ids           # дубль скрыт, основной остался
    notes = [n["text"] for n in c.get(f"/api/patients/{a['id']}/notes", headers=H).json()]
    assert "заметка на дубле" in notes                      # заметка переехала
