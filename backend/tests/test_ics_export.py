"""Экспорт .ics — заголовки обезличены (152-ФЗ): без ФИО и диагноза пациента."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.db import engine
from app.services.billing import apply_payment
from app.models import Doctor, Patient, Appointment, Reminder
from app.services.identity import name_index_for
from sqlmodel import Session, select

seed.run()
c = TestClient(app)


def _login(email):
    c.post("/api/auth/register", json={"email": email, "phone": "+7900" + str(abs(hash(email)) % 10**7).zfill(7), "password": "pass12345", "full_name": "Врач"})
    r = c.post("/api/auth/login", json={"email": email, "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": email, "code": r["dev_code"], "device_id": "d"}).json()
    with Session(engine) as s:
        d = s.exec(select(Doctor).where(Doctor.email == email)).first()
        apply_payment(s, d.id, "1m")
    return {"Authorization": "Bearer " + v["token"]}, v["doctor"]["id"]


H, DID = _login("ics_a@x.ru")


def test_ics_has_no_patient_name_or_diagnosis():
    # пациент с говорящей фамилией и диагнозом в причине приёма
    with Session(engine) as s:
        p = Patient(doctor_id=DID, last_name="Секретов", first_name="Тайномир",
                    name_index=name_index_for("Секретов", "Тайномир"))
        s.add(p); s.commit(); s.refresh(p)
        s.add(Appointment(doctor_id=DID, patient_id=p.id, kind="repeat", status="planned",
                          starts_at=clock.now() + timedelta(days=1), reason="рак предстательной железы"))
        s.add(Reminder(doctor_id=DID, patient_id=p.id, title="Контроль ПСА Секретов рак",
                       kind="control", status="open", due_at=clock.now() + timedelta(days=2)))
        s.commit()
    r = c.get("/api/calendar/export.ics", headers=H)
    assert r.status_code == 200
    body = r.text
    # НИ ФИО, ни диагноз не должны попасть в файл
    assert "Секретов" not in body
    assert "Тайномир" not in body
    assert "рак" not in body.lower()
    # но обезличенные события есть
    assert "Повторный приём" in body
    assert "Контроль" in body
    assert "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body


def test_ics_content_type_and_attachment():
    r = c.get("/api/calendar/export.ics", headers=H)
    assert "text/calendar" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
