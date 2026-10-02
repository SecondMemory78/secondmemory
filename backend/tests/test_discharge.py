"""Выписка по эпизоду.

Главное правило: в документ идёт только подтверждённое, а всё остальное не
исчезает молча — оно попадает в панель исключённого с причиной. Врач
подписывает выписку своим именем и должен знать о пропуске ДО подписи.
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
from app.models import (Device, Encounter, Observation, PatientDiagnosis,
                        Prescription, Procedure)

seed.run()
c = TestClient(app)


def _setup():
    # Свой пациент, а не первый попавшийся: тестовые файлы делят одну базу
    # (DATABASE_URL ставится первым импортом), и соседний тест переназначал
    # основной диагноз — выписка собиралась с чужим N13.
    from app.models import Patient
    with Session(engine) as s:
        p = Patient(doctor_id=1, last_name="Выписнов", first_name="Пётр",
                    middle_name="Иванович", birth_date=date(1960, 5, 1))
        s.add(p); s.commit(); s.refresh(p)
        pid = p.id
        enc = Encounter(doctor_id=1, patient_id=pid, type="visit", reason="приём",
                        started_at=clock.now() - timedelta(days=10))
        s.add(enc); s.commit(); s.refresh(enc)

        s.add(PatientDiagnosis(patient_id=pid, code="N40", title="Гиперплазия",
                               is_primary=True, confirmed=True))
        s.add(PatientDiagnosis(patient_id=pid, code="N21", title="Камень",
                               confirmed=False, source="ai_suggested"))
        s.add(Procedure(patient_id=pid, name="ТУР простаты", confirmed=True,
                        performed_at=date.today() - timedelta(days=3)))
        s.add(Procedure(patient_id=pid, name="Без даты", confirmed=True))
        s.add(Observation(patient_id=pid, parameter_code="psa_total", value_num=4.8,
                          unit="нг/мл", effective_date=date.today(), status="confirmed"))
        s.add(Observation(patient_id=pid, parameter_code="creatinine", value_num=99,
                          unit="мкмоль/л", effective_date=date.today(), status="pending"))
        s.add(Prescription(patient_id=pid, drug_name="Тамсулозин", dose="0,4 мг",
                           status="active", confirmed=True))
        s.add(Device(doctor_id=1, patient_id=pid, kind="stent", side="right",
                     active=True, installed_at=date.today() - timedelta(days=3)))
        s.commit()
        return pid, enc.id


PID, EID = _setup()


def _draft():
    r = c.post(f"/api/encounters/{EID}/discharge")
    assert r.status_code == 200, r.text
    return r.json()


def test_черновик_собирается_из_подтверждённого():
    d = _draft()
    assert d["status"] == "draft"
    assert d["sections"]["diagnosis_main"].startswith("N40")
    assert any(p["name"] == "ТУР простаты" for p in d["sections"]["procedures"])
    assert any(o["code"] == "psa_total" for o in d["sections"]["investigations"])


def test_неподтверждённое_не_исчезает_молча():
    """Врач должен видеть, чего в выписке нет и почему."""
    d = _draft()
    reasons = {x["what"]: x["why"] for x in d["excluded"]}
    assert any("N21" in w or "Камень" in w for w in reasons), "неподтверждённый диагноз не отмечен"
    assert any("creatinine" in w for w in reasons), "ожидающий показатель не отмечен"
    assert any("Без даты" in w for w in reasons), "операция без даты не отмечена"


def test_повторный_вызов_не_плодит_черновики():
    a, b = _draft()["id"], _draft()["id"]
    assert a == b


def test_проверки_предупреждают_а_не_запрещают():
    d = _draft()
    codes = {x["code"] for x in d["checks"]}
    assert "D4" in codes, "устройство без срока замены должно предупреждать"
    assert "D6" in codes, "про ожидающие подтверждения должно быть сказано"
    # и всё же подписать можно
    assert c.post(f"/api/discharge/{d['id']}/finalize").status_code == 200


def test_подписанную_менять_нельзя():
    d = _draft()
    c.post(f"/api/discharge/{d['id']}/finalize")
    r = c.patch(f"/api/discharge/{d['id']}", json={"sections": {"diagnosis_main": "подмена"}})
    assert r.status_code == 400
    assert "подписан" in r.json()["detail"].lower()


def test_новая_версия_не_трогает_старую():
    d = _draft()
    c.post(f"/api/discharge/{d['id']}/finalize")
    new = c.post(f"/api/discharge/{d['id']}/revise").json()
    assert new["version"] == d["version"] + 1 and new["status"] == "draft"
    old = c.get(f"/api/discharge/{d['id']}").json()
    assert old["status"] == "final", "подписанная версия изменилась"


def test_правка_врача_сохраняется():
    d = c.post(f"/api/encounters/{EID}/discharge").json()
    if d["status"] == "final":
        d = c.post(f"/api/discharge/{d['id']}/revise").json()
    sec = dict(d["sections"]); sec["diagnosis_main"] = "N40 ДГПЖ, моя формулировка"
    r = c.patch(f"/api/discharge/{d['id']}", json={"sections": sec})
    assert r.status_code == 200
    assert r.json()["sections"]["diagnosis_main"] == "N40 ДГПЖ, моя формулировка"


def test_чужая_выписка_не_отдаётся():
    assert c.get("/api/discharge/999999").status_code == 404


def test_пустые_разделы_не_придумываются():
    """Раздела нет — значит нет. Никаких «без особенностей»."""
    from app.models import Patient
    with Session(engine) as s:
        p2 = Patient(doctor_id=1, last_name="Пустов", first_name="Иван", middle_name="")
        s.add(p2); s.commit(); s.refresh(p2)
        enc = Encounter(doctor_id=1, patient_id=p2.id, type="visit", reason="пустой")
        s.add(enc); s.commit(); s.refresh(enc)
        eid2 = enc.id
    d = c.post(f"/api/encounters/{eid2}/discharge").json()
    text = str(d["sections"])
    for word in ("особенностей", "удовлетворительное", "норма", "здоров"):
        assert word not in text


def test_выписка_только_по_своему_эпизоду():
    """Раньше в выписку попадала вся история пациента, включая анализы
    двухлетней давности. Это документ ПО ЭПИЗОДУ."""
    from app.models import Patient
    with Session(engine) as s:
        p = Patient(doctor_id=1, last_name="Эпизодов", first_name="Иван", middle_name="")
        s.add(p); s.commit(); s.refresh(p)
        enc = Encounter(doctor_id=1, patient_id=p.id, type="visit", reason="этот",
                        started_at=clock.now() - timedelta(days=5))
        s.add(enc); s.commit(); s.refresh(enc)
        # свежий — внутри эпизода
        s.add(Observation(patient_id=p.id, parameter_code="psa_total", value_num=5.0,
                          unit="нг/мл", effective_date=date.today(), status="confirmed"))
        # старый — за год до эпизода
        s.add(Observation(patient_id=p.id, parameter_code="psa_total", value_num=1.2,
                          unit="нг/мл", effective_date=date.today() - timedelta(days=400),
                          status="confirmed"))
        s.commit(); eid = enc.id

    d = c.post(f"/api/encounters/{eid}/discharge").json()
    values = [o["value"] for o in d["sections"].get("investigations", [])]
    assert 5.0 in values
    assert 1.2 not in values, "в выписку попал анализ из другого периода"


def test_вне_сроков_не_исчезает_молча_но_одной_строкой():
    """Перечислять годы наблюдения поимённо нельзя — панель станет простынёй."""
    from app.models import Patient
    with Session(engine) as s:
        p = Patient(doctor_id=1, last_name="Старов", first_name="Пётр", middle_name="")
        s.add(p); s.commit(); s.refresh(p)
        enc = Encounter(doctor_id=1, patient_id=p.id, type="visit", reason="этот",
                        started_at=clock.now() - timedelta(days=2))
        s.add(enc); s.commit(); s.refresh(enc)
        for i in range(4):
            s.add(Observation(patient_id=p.id, parameter_code="psa_total", value_num=1.0 + i,
                              unit="нг/мл", effective_date=date.today() - timedelta(days=300 + i),
                              status="confirmed"))
        s.commit(); eid = enc.id

    d = c.post(f"/api/encounters/{eid}/discharge").json()
    outside = [x for x in d["excluded"] if "вне сроков" in x["what"]]
    assert len(outside) == 1, "должна быть одна строка, а не четыре"
    assert "4" in outside[0]["what"]
