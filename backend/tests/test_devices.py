"""Устройства C02 — Часть 1: создание/список, валидация типа, изоляция врача."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from app.services.billing import apply_payment
from app.models import Doctor, Patient
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


H, DID = _login("dev_a@x.ru")
HB, DIDB = _login("dev_b@x.ru")


def _mk_patient(did, ln="Устройсев"):
    with Session(engine) as s:
        p = Patient(doctor_id=did, last_name=ln, first_name="Пётр", sex="м",
                    name_index=name_index_for(ln, "Пётр"))
        s.add(p); s.commit(); s.refresh(p)
        return p.id


PID = _mk_patient(DID)


def test_add_and_list_device():
    r = c.post(f"/api/patients/{PID}/devices", headers=H,
               json={"kind": "stent", "device_label": "стент справа", "due_at": "2026-07-01"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kind"] == "stent" and d["active"] is True and d["due_at"] == "2026-07-01"
    lst = c.get(f"/api/patients/{PID}/devices", headers=H).json()
    assert any(x["id"] == d["id"] for x in lst["items"])


def test_device_no_due_allowed():
    r = c.post(f"/api/patients/{PID}/devices", headers=H, json={"kind": "catheter"})
    assert r.status_code == 200
    assert r.json()["due_at"] is None            # «срок не задан» допустим


def test_invalid_kind_rejected():
    r = c.post(f"/api/patients/{PID}/devices", headers=H, json={"kind": "bogus"})
    assert r.status_code == 400


def test_devices_doctor_isolated():
    # врач B не может ни читать, ни заводить устройства пациенту врача A
    assert c.get(f"/api/patients/{PID}/devices", headers=HB).status_code == 404
    assert c.post(f"/api/patients/{PID}/devices", headers=HB,
                  json={"kind": "stent"}).status_code == 404


def _add(pid, kind="stent", **kw):
    return c.post(f"/api/patients/{pid}/devices", headers=H, json={"kind": kind, **kw}).json()


def test_close_marks_inactive():
    d = _add(PID, "nephrostomy", device_label="нефростома слева")
    r = c.post(f"/api/patients/{PID}/devices/{d['id']}/close", headers=H, json={"action": "removed"})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is False and body["closed_action"] == "removed" and body["closed_at"]


def test_close_twice_conflicts():
    d = _add(PID, "catheter")
    c.post(f"/api/patients/{PID}/devices/{d['id']}/close", headers=H, json={})
    r2 = c.post(f"/api/patients/{PID}/devices/{d['id']}/close", headers=H, json={})
    assert r2.status_code == 409           # уже закрыто


def test_replace_closes_old_opens_new_only():
    # два активных устройства; заменяем ОДНО — второе не должно пострадать
    keep = _add(PID, "stent", device_label="стент справа")
    old = _add(PID, "stent", device_label="стент слева")
    r = c.post(f"/api/patients/{PID}/devices/{old['id']}/replace", headers=H,
               json={"device_label": "стент слева (новый)", "due_at": "2026-12-01"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["closed"]["active"] is False and res["closed"]["closed_action"] == "replaced"
    assert res["new"]["active"] is True and res["new"]["device_label"] == "стент слева (новый)"
    assert res["new"]["id"] != old["id"]
    # второе устройство (keep) всё ещё активно
    lst = c.get(f"/api/patients/{PID}/devices", headers=H).json()["items"]
    keep_row = [x for x in lst if x["id"] == keep["id"]][0]
    assert keep_row["active"] is True


def test_replace_keeps_kind_by_default():
    d = _add(PID, "nephrostomy")
    r = c.post(f"/api/patients/{PID}/devices/{d['id']}/replace", headers=H, json={})
    assert r.json()["new"]["kind"] == "nephrostomy"    # тип наследуется


def test_lifecycle_actions_doctor_isolated():
    d = _add(PID, "stent")
    assert c.post(f"/api/patients/{PID}/devices/{d['id']}/close", headers=HB, json={}).status_code == 404
    assert c.post(f"/api/patients/{PID}/devices/{d['id']}/replace", headers=HB, json={}).status_code == 404
