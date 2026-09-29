"""Шаблоны приёмов: встроенные T01-T12, свои, применение в протоколе."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def test_builtin_templates_present():
    r = c.get("/api/templates", headers=H).json()
    codes = [t["code"] for t in r["builtin"]]
    assert "T01" in codes and "T06" in codes and "T12" in codes and len(codes) == 12
    t6 = c.get("/api/templates/T06", headers=H).json()
    assert "ПСА" in t6["additional"] and "PI-RADS" in t6["exam_docs"]


def test_save_and_edit_custom_template():
    saved = c.post("/api/templates", headers=H, json={"name": "Мой ДГПЖ", "based_on": "T01",
        "additional": "своё поле", "plan": "свой план"}).json()
    assert saved["code"].startswith("custom:") and saved["version"] == 1
    tid = saved["id"]
    upd = c.patch(f"/api/templates/custom/{tid}", headers=H,
                  json={"expected_version": 1, "plan": "обновлённый план"}).json()
    assert upd["plan"] == "обновлённый план" and upd["version"] == 2
    # конфликт версий
    assert c.patch(f"/api/templates/custom/{tid}", headers=H, json={"expected_version": 1, "name": "x"}).status_code == 409
    # в списке появился личный
    r = c.get("/api/templates", headers=H).json()
    assert any(x["id"] == tid for x in r["custom"])
    # удаление
    c.delete(f"/api/templates/custom/{tid}", headers=H)
    r2 = c.get("/api/templates", headers=H).json()
    assert not any(x["id"] == tid for x in r2["custom"])


def test_protocol_stores_template_blocks():
    pid = c.get("/api/patients", headers=H).json()[0]["id"]
    c.put(f"/api/patients/{pid}/protocol", headers=H, json={
        "complaints": "никтурия", "template_code": "T01",
        "tpl_additional": "IPSS 18, QoL 4", "tpl_plan": "урофлоуметрия, контроль через месяц"})
    p = c.get(f"/api/patients/{pid}/protocol", headers=H).json()
    assert p["template_code"] == "T01" and "IPSS" in p["tpl_additional"]
