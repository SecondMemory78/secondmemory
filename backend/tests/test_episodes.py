"""Задача 2: эпизоды/госпитализации, день пребывания, версии, больничный, выбор эпизода."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def _pid():
    """Свежий пациент с согласием — чтобы тесты эпизодов не пересекались с другими."""
    import uuid
    pid = c.post("/api/patients", headers=H,
                 json={"last_name": "Эпизодов", "first_name": uuid.uuid4().hex[:6]}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H)
    return pid


def test_create_hospitalization_and_day_of_stay():
    pid = _pid()
    adm = (clock.today() - timedelta(days=2)).isoformat() + "T10:00:00"
    e = c.post(f"/api/patients/{pid}/episodes", headers=H,
               json={"type": "hospitalization", "reason": "камень почки", "ward": "3", "actual_admission_at": adm,
                     "diagnosis_code": "N20.0", "diagnosis_text": "Камень почки"}).json()
    assert e["type"] == "hospitalization" and e["ward"] == "3"
    assert e["day_of_stay"] == 3               # поступил 2 дня назад → сегодня 3-й день
    assert e["diagnosis_code"] == "N20.0"      # диагноз эпизода


def test_day_of_stay_none_without_admission_date():
    pid = _pid()
    e = c.post(f"/api/patients/{pid}/episodes", headers=H,
               json={"type": "hospitalization", "reason": "без даты"}).json()
    assert e["day_of_stay"] is None            # дату не выдумываем


def test_episode_version_conflict():
    pid = _pid()
    e = c.post(f"/api/patients/{pid}/episodes", headers=H, json={"type": "visit"}).json()
    # первое обновление ок
    r1 = c.patch(f"/api/episodes/{e['id']}", headers=H, json={"expected_version": 1, "ward": "5"})
    assert r1.status_code == 200 and r1.json()["version"] == 2
    # повтор со старой версией → конфликт
    r2 = c.patch(f"/api/episodes/{e['id']}", headers=H, json={"expected_version": 1, "ward": "6"})
    assert r2.status_code == 409


def test_multiple_open_episodes_ask_which():
    # свежему пациенту два открытых эпизода → добавление заметки спрашивает, куда
    pid = _pid()
    c.post(f"/api/patients/{pid}/episodes", headers=H, json={"type": "visit"})
    c.post(f"/api/patients/{pid}/episodes", headers=H, json={"type": "hospitalization"})
    r = c.post(f"/api/patients/{pid}/notes", headers=H, params={"text": "куда-то"})
    assert r.status_code == 409 and r.json()["detail"]["ambiguous"] is True
    eid = r.json()["detail"]["episodes"][0]["id"]
    # с явным эпизодом — ок
    r2 = c.post(f"/api/patients/{pid}/notes", headers=H, params={"text": "в конкретный", "encounter_id": eid})
    assert r2.status_code == 200 and r2.json()["encounter_id"] == eid


def test_sick_leave_lifecycle_independent_of_discharge():
    pid = _pid()
    sl = c.post(f"/api/patients/{pid}/sick-leaves", headers=H, json={"number": "БЛ-1"}).json()
    assert sl["status"] == "open"
    # продлить
    r = c.patch(f"/api/sick-leaves/{sl['id']}", headers=H, json={"expected_version": 1, "status": "extended"}).json()
    assert r["status"] == "extended" and r["version"] == 2
    # закрыть
    r2 = c.patch(f"/api/sick-leaves/{sl['id']}", headers=H,
                 json={"expected_version": 2, "status": "closed", "closed_at": clock.today().isoformat()}).json()
    assert r2["status"] == "closed"


def test_old_visit_flow_still_works():
    pid = _pid()
    e = c.post(f"/api/patients/{pid}/encounters", headers=H, json={"reason": "обычный приём"}).json()
    assert e["type"] == "visit" and e["status"] == "open"
