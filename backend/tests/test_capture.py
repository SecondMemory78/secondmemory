"""Захват фотографией: направление → предложение задачи или записи.

Два правила: предложение не становится записью само (распознавание ошибается в
датах и фамилиях, а задача с неверным сроком хуже её отсутствия — врач на неё
рассчитывает), и распознавание идёт фоном.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Reminder, Appointment, SourceDocument

seed.run()
c = TestClient(app)
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _capture():
    r = c.post("/api/capture", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["capture_id"]


def test_снимок_принимается_сразу():
    r = c.post("/api/capture", files={"file": ("a.png", PNG, "image/png")})
    d = r.json()
    assert d["ocr_status"] == "queued"
    assert "продолжать" in d["message"].lower()


def test_текст_и_предложение_доезжают():
    cid = _capture()
    got = c.get(f"/api/capture/{cid}").json()
    assert got["ocr_status"] == "done"
    assert got["text"]
    assert got["proposal"]["kind"] in ("task", "appointment")
    assert got["proposal"]["title"]


def test_до_подтверждения_ничего_не_создаётся():
    """В базе только распознанный текст — ни задачи, ни приёма."""
    with Session(engine) as s:
        before_t = len(s.exec(select(Reminder)).all())
        before_a = len(s.exec(select(Appointment)).all())
    _capture()
    with Session(engine) as s:
        assert len(s.exec(select(Reminder)).all()) == before_t
        assert len(s.exec(select(Appointment)).all()) == before_a


def test_подтверждение_создаёт_задачу():
    cid = _capture()
    r = c.post(f"/api/capture/{cid}/accept", json={"kind": "task", "title": "Заказать стенты"})
    assert r.status_code == 200, r.text
    assert r.json()["intent"] == "task"
    with Session(engine) as s:
        assert s.exec(select(Reminder).where(
            Reminder.title == "Заказать стенты")).first()


def test_правка_врача_важнее_разбора():
    """Врач поправил заголовок — создаём его вариант, а не распознанный."""
    cid = _capture()
    r = c.post(f"/api/capture/{cid}/accept",
               json={"kind": "task", "title": "Моя формулировка"})
    assert "Моя формулировка" in r.json()["message"]


def test_приём_без_времени_не_создаётся():
    cid = _capture()
    r = c.post(f"/api/capture/{cid}/accept", json={"kind": "appointment"})
    assert r.status_code == 400
    assert "время" in r.json()["detail"].lower()


def test_фото_не_хранится():
    cid = _capture()
    with Session(engine) as s:
        doc = s.get(SourceDocument, cid)
        assert doc.image_purged is True and doc.storage_ref == ""


def test_чужой_снимок_не_отдаётся():
    assert c.get("/api/capture/999999").status_code == 404


def test_тёзки_не_выбираются_за_врача():
    from app.routers.capture import _proposal
    from app.models import Patient
    from app.deps import set_current_doctor_id
    set_current_doctor_id(1)
    with Session(engine) as s:
        s.add(Patient(doctor_id=1, last_name="Иванов", first_name="Сергей", middle_name=""))
        s.commit()
        out = _proposal(s, "Иванов, контроль ПСА")
        if out.get("ambiguous_patients"):
            assert out["patient_id"] is None, "при тёзках пациент выбран сам"


# ── снимок из шторки ассистента: куда он попадёт ────────────────────────────
# Открытая карта — подсказка, а не ответ: врачу приносят чужие бумаги прямо
# на приёме. Поэтому подтверждает всегда врач.

def _capture_ctx(pid):
    r = c.post("/api/capture", files={"file": ("a.png", PNG, "image/png")},
               data={"context_patient_id": str(pid)})
    assert r.status_code == 200, r.text
    return r.json()["capture_id"]


def test_открытая_карта_предлагается_но_не_решает():
    pid = c.get("/api/patients").json()[0]["id"]
    got = c.get(f"/api/capture/{_capture_ctx(pid)}").json()
    assert got["proposal"]["patient_id"] == pid
    assert got["proposal"]["patient_from"] == "открытая карта"


def test_без_контекста_пациент_не_подставляется_из_воздуха():
    got = c.get(f"/api/capture/{_capture()}").json()
    p = got["proposal"]
    assert p.get("patient_from") in (None, "фамилия в документе")


def test_документ_в_карту_кладёт_значения_на_подтверждение():
    from app.models import Observation, SourceDocument
    pid = c.get("/api/patients").json()[0]["id"]
    cid = _capture_ctx(pid)
    r = c.post(f"/api/capture/{cid}/accept",
               json={"kind": "document", "patient_id": pid})
    assert r.status_code == 200, r.text
    assert r.json()["intent"] == "document"
    with Session(engine) as s:
        doc = s.get(SourceDocument, cid)
        assert doc.patient_id == pid
        vals = s.exec(select(Observation).where(
            Observation.source_document_id == cid)).all()
        for o in vals:
            assert o.status == "pending", "значение попало в карту без врача"


def test_документ_без_пациента_не_принимается():
    cid = _capture()
    r = c.post(f"/api/capture/{cid}/accept", json={"kind": "document"})
    assert r.status_code == 400
    assert "чью карту" in r.json()["detail"].lower()


def test_врач_может_выбрать_другого_пациента():
    """Предложение — не приговор: врач указывает своего."""
    pts = c.get("/api/patients").json()
    cid = _capture_ctx(pts[0]["id"])
    r = c.post(f"/api/capture/{cid}/accept",
               json={"kind": "document", "patient_id": pts[1]["id"]})
    assert r.status_code == 200
    assert r.json()["patient_id"] == pts[1]["id"]
