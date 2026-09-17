"""Согласие 152-ФЗ как барьер: без согласия приём нельзя; 3 способа; проверка бланка;
фото не хранится."""
import os, tempfile, io
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _new_patient():
    return c.post("/api/patients", json={"last_name": "Тестов", "first_name": "Иван",
                                         "birth_date": "1970-05-01"}).json()["id"]


def test_new_patient_blocks_prescribe_until_consent():
    pid = _new_patient()
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is False
    r = c.post(f"/api/patients/{pid}/prescriptions", json={"drug_name": "Тамсулозин"})
    assert r.status_code == 403                       # барьер: без согласия нельзя
    # старт визита тоже заблокирован
    assert c.post(f"/api/patients/{pid}/encounters", json={}).status_code == 403


def test_electronic_consent_unblocks():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is True
    assert c.post(f"/api/patients/{pid}/prescriptions", json={"drug_name": "Тамсулозин"}).json()["saved"] is True


def test_electronic_requires_agreement():
    pid = _new_patient()
    assert c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": False}).status_code == 400


def test_paper_consent_ai_verifies_and_stores_text_not_photo():
    pid = _new_patient()
    fake = io.BytesIO(b"\xff\xd8\xff fake jpeg bytes")
    r = c.post(f"/api/patients/{pid}/consent/paper",
               files={"photo": ("blank.jpg", fake, "image/jpeg")}).json()
    assert r["consent_ok"] is True and r["verified"] is True
    assert "Тестов" in r["form_text"]                 # хранится распознанный текст…
    # …а само фото как документ НЕ создано (минимизация ПДн)
    from sqlmodel import Session, select
    from app.db import engine
    from app.models import SourceDocument
    with Session(engine) as s:
        docs = s.exec(select(SourceDocument).where(SourceDocument.patient_id == pid)).all()
    assert len(docs) == 0


def test_demo_patients_have_consent():
    pid = c.get("/api/patients").json()[0]["id"]
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is True


def test_consent_blocks_all_record_writes():
    """Без согласия нельзя вносить НИЧЕГО в карту: показатель, заметка, диагноз, протокол, документ."""
    pid = _new_patient()
    assert c.post(f"/api/patients/{pid}/observations", json={"parameter_code": "psa_total", "value_num": 5}).status_code == 403
    assert c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы"}).status_code == 403
    assert c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40.0", "title": "ДГПЖ"}).status_code == 403
    assert c.put(f"/api/patients/{pid}/protocol", json={"complaints": "x"}).status_code == 403
    # после согласия — можно
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    assert c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы"}).status_code == 200
