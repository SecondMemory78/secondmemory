"""Готовые списки C03/C04/C05 (ТЗ §11): правила попадания, дедуп, изоляция врача."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta, date
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
from app.db import engine
from app.services.billing import apply_payment
from app.models import (Doctor, Patient, Appointment, Observation, Encounter, SickLeave, Reminder)
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


H, DID = _login("lists_a@x.ru")
HB, DIDB = _login("lists_b@x.ru")


def _mk_patient(did, ln="Тестов"):
    with Session(engine) as s:
        from app.services.identity import name_index_for
        p = Patient(doctor_id=did, last_name=ln, first_name="Пётр", sex="м",
                    name_index=name_index_for(ln, "Пётр"))
        s.add(p); s.commit(); s.refresh(p)
        return p.id


def test_c03_overdue_repeat_appears_confirmed_does_not():
    pid = _mk_patient(DID, "Птицын")
    other = _mk_patient(DID, "Птахин")
    with Session(engine) as s:
        # просроченный запланированный повтор → должен попасть
        s.add(Appointment(doctor_id=DID, patient_id=pid, kind="repeat", status="planned",
                          starts_at=clock.now() - timedelta(days=3)))
        # подтверждённый (done) повтор → НЕ должен попасть
        s.add(Appointment(doctor_id=DID, patient_id=other, kind="repeat", status="done",
                          starts_at=clock.now() - timedelta(days=3)))
        s.commit()
    r = c.get("/api/lists/C03", headers=H).json()
    ids = [it["patient_id"] for it in r["items"]]
    assert pid in ids
    assert other not in ids


def test_c04_pending_result_appears():
    pid = _mk_patient(DID, "Ждущев")
    with Session(engine) as s:
        s.add(Observation(patient_id=pid, parameter_code="psa_total", value_num=5.0,
                          status="pending", effective_date=date.today()))
        # подтверждённый результат того же пациента не должен создавать вторую строку
        s.add(Observation(patient_id=pid, parameter_code="psa_total", value_num=4.0,
                          status="confirmed", effective_date=date.today()))
        s.commit()
    r = c.get("/api/lists/C04", headers=H).json()
    ids = [it["patient_id"] for it in r["items"]]
    assert ids.count(pid) == 1        # дедуп: одна строка на пациента


def test_c05_discharge_and_open_sickleave():
    pid = _mk_patient(DID, "Выписов")
    with Session(engine) as s:
        s.add(Encounter(doctor_id=DID, patient_id=pid, type="hospitalization", status="open",
                        planned_discharge_at=clock.now() + timedelta(days=1)))
        s.add(SickLeave(doctor_id=DID, patient_id=pid, status="open", opened_at=date.today()))
        s.commit()
    r = c.get("/api/lists/C05", headers=H).json()
    row = [it for it in r["items"] if it["patient_id"] == pid]
    assert len(row) == 1              # обе причины объединены в одну строку
    assert "выписк" in row[0]["reason"].lower() and "больничный" in row[0]["reason"].lower()


def test_lists_are_doctor_isolated():
    pid = _mk_patient(DID, "Чужов")
    with Session(engine) as s:
        s.add(Appointment(doctor_id=DID, patient_id=pid, kind="repeat", status="planned",
                          starts_at=clock.now() - timedelta(days=5)))
        s.commit()
    # врач B не видит пациента врача A ни в одном списке
    rb = c.get("/api/lists/C03", headers=HB).json()
    assert all(it["patient_id"] != pid for it in rb["items"])


def test_all_lists_returns_presets_with_counts():
    r = c.get("/api/lists", headers=H).json()
    codes = {p["code"] for p in r["presets"]}
    assert {"C03", "C04", "C05"}.issubset(codes)
    for p in r["presets"]:
        assert "count" in p and "title" in p


def test_unknown_list_404():
    assert c.get("/api/lists/C99", headers=H).status_code == 404


def test_c01_overdue_psa_control_without_result_appears():
    pid = _mk_patient(DID, "Псаев")
    with Session(engine) as s:
        s.add(Reminder(doctor_id=DID, patient_id=pid, title="Контроль ПСА", kind="control",
                       parameter_code="psa_total", status="open",
                       due_at=clock.now() - timedelta(days=2)))
        s.commit()
    r = c.get("/api/lists/C01", headers=H).json()
    assert pid in [it["patient_id"] for it in r["items"]]


def test_c01_closed_by_confirmed_result():
    pid = _mk_patient(DID, "Закрытов")
    with Session(engine) as s:
        due = clock.now() - timedelta(days=5)
        s.add(Reminder(doctor_id=DID, patient_id=pid, title="Контроль ПСА", kind="control",
                       parameter_code="psa_total", status="open", due_at=due))
        # подтверждённый результат ПСА после срока назначения → пункт закрыт
        s.add(Observation(patient_id=pid, parameter_code="psa_total", value_num=3.2,
                          status="confirmed", effective_date=due.date() + timedelta(days=1)))
        s.commit()
    r = c.get("/api/lists/C01", headers=H).json()
    assert pid not in [it["patient_id"] for it in r["items"]]


def test_c01_pending_result_does_not_close_stays_out_of_c01_but_in_c04():
    pid = _mk_patient(DID, "Ожиданов")
    with Session(engine) as s:
        due = clock.now() - timedelta(days=3)
        s.add(Reminder(doctor_id=DID, patient_id=pid, title="Контроль ПСА", kind="control",
                       parameter_code="psa_total", status="open", due_at=due))
        # результат получен, но НЕ подтверждён (pending) — не закрывает C01, но виден в C04
        s.add(Observation(patient_id=pid, parameter_code="psa_total", value_num=6.0,
                          status="pending", effective_date=due.date() + timedelta(days=1)))
        s.commit()
    c01 = c.get("/api/lists/C01", headers=H).json()
    c04 = c.get("/api/lists/C04", headers=H).json()
    assert pid in [it["patient_id"] for it in c01["items"]]   # ещё не оценён → всё ещё C01
    assert pid in [it["patient_id"] for it in c04["items"]]   # и одновременно ждёт разбора → C04


def test_c01_no_due_shows_as_undated():
    pid = _mk_patient(DID, "Бессрочев")
    with Session(engine) as s:
        s.add(Reminder(doctor_id=DID, patient_id=pid, title="Контроль ПСА", kind="control",
                       parameter_code="psa_total", status="open", due_at=None))
        s.commit()
    r = c.get("/api/lists/C01", headers=H).json()
    row = [it for it in r["items"] if it["patient_id"] == pid]
    assert len(row) == 1 and row[0]["due"] is None
    assert "не задан" in row[0]["reason"].lower()


def test_c02_active_device_due_soon_appears():
    from app.models import Device
    pid = _mk_patient(DID, "Стентов")
    with Session(engine) as s:
        s.add(Device(doctor_id=DID, patient_id=pid, kind="stent", device_label="справа",
                     active=True, due_at=(clock.now().date() + timedelta(days=3))))
        s.commit()
    r = c.get("/api/lists/C02", headers=H).json()
    assert pid in [it["patient_id"] for it in r["items"]]


def test_c02_closed_device_excluded():
    from app.models import Device
    pid = _mk_patient(DID, "Снятов")
    with Session(engine) as s:
        s.add(Device(doctor_id=DID, patient_id=pid, kind="catheter", active=False,
                     due_at=(clock.now().date() - timedelta(days=1))))
        s.commit()
    r = c.get("/api/lists/C02", headers=H).json()
    assert pid not in [it["patient_id"] for it in r["items"]]


def test_c02_two_devices_one_row():
    from app.models import Device
    pid = _mk_patient(DID, "Двойнов")
    with Session(engine) as s:
        s.add(Device(doctor_id=DID, patient_id=pid, kind="stent", device_label="левый",
                     active=True, due_at=(clock.now().date() + timedelta(days=2))))
        s.add(Device(doctor_id=DID, patient_id=pid, kind="nephrostomy",
                     active=True, due_at=None))
        s.commit()
    r = c.get("/api/lists/C02", headers=H).json()
    rows = [it for it in r["items"] if it["patient_id"] == pid]
    assert len(rows) == 1                        # дедуп: одна строка на пациента
    assert "стент" in rows[0]["reason"].lower() and "нефростома" in rows[0]["reason"].lower()


def test_c02_doctor_isolated():
    from app.models import Device
    pid = _mk_patient(DID, "Тайнов")
    with Session(engine) as s:
        s.add(Device(doctor_id=DID, patient_id=pid, kind="stent", active=True,
                     due_at=(clock.now().date() - timedelta(days=1))))
        s.commit()
    rb = c.get("/api/lists/C02", headers=HB).json()
    assert all(it["patient_id"] != pid for it in rb["items"])
