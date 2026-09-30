"""Сторона устройства.

Для урологии «стент справа» и «стент слева» — разные устройства и разные
действия. Раньше сторону можно было записать только текстом в метку, и в
памятку она попадала как придётся.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.pdf_export import handout_sections

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def test_сторона_сохраняется_и_подписывается():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/devices",
               json={"kind": "stent", "side": "right", "due_at": "2026-11-09"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["side"] == "right" and d["side_label"] == "справа"


def test_неизвестная_сторона_отклоняется():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/devices", json={"kind": "stent", "side": "верх"})
    assert r.status_code == 400


def test_при_замене_сторона_наследуется():
    """Замена стента справа на стент слева — почти наверняка ошибка ввода."""
    pid = _pid()
    old = c.post(f"/api/patients/{pid}/devices", json={"kind": "stent", "side": "left"}).json()
    r = c.post(f"/api/patients/{pid}/devices/{old['id']}/replace", json={})
    assert r.status_code == 200, r.text
    assert r.json()["new"]["side"] == "left"


def test_сторону_можно_сменить_явно():
    pid = _pid()
    old = c.post(f"/api/patients/{pid}/devices", json={"kind": "stent", "side": "left"}).json()
    r = c.post(f"/api/patients/{pid}/devices/{old['id']}/replace", json={"side": "right"})
    assert r.json()["new"]["side"] == "right"


def test_сторона_попадает_в_памятку():
    s = {x["key"]: x for x in handout_sections(
        {"observations": [], "prescriptions": [], "appointments": [],
         "devices": [{"kind": "stent", "side": "right", "active": True,
                      "installed_at": "2026-09-10", "due_at": "2026-11-09"}]})}
    assert "справа" in s["devices"]["rows"][0][0]


def test_закрытие_ставит_состояние():
    pid = _pid()
    d = c.post(f"/api/patients/{pid}/devices", json={"kind": "catheter"}).json()
    c.post(f"/api/patients/{pid}/devices/{d['id']}/close", json={"action": "removed"})
    items = c.get(f"/api/patients/{pid}/devices").json()["items"]
    closed = [x for x in items if x["id"] == d["id"]][0]
    assert closed["state"] == "removed" and closed["active"] is False
