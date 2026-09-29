"""T8. Аллергобезопасность по справочнику: групповой конфликт, красный флаг,
перекрёстное правило в ответе, никакой блокировки/автозамены."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _sergeeva():
    return [p for p in c.get("/api/patients").json() if p["last_name"] == "Сергеева"][0]["id"]


def test_group_conflict_detected_from_dictionary():
    pid = _sergeeva()  # аллергия на фторхинолоны
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Ципрофлоксацин", "dose": "500 мг"}).json()
    assert r["conflict"] is True and r["saved"] is False
    assert "Фторхинолон" in r["message"]
    assert r["level"] == "high"                 # группа помечена красным в справочнике
    assert r["cross_rule"]                       # правило перекрёстности показано врачу


def test_no_conflict_for_unrelated_drug():
    pid = _sergeeva()
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Тамсулозин", "dose": "0.4 мг"}).json()
    assert r["conflict"] is False and r["saved"] is True


def test_override_saves_with_reason_not_blocked():
    pid = _sergeeva()
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Левофлоксацин", "dose": "500 мг",
                     "override_reason": "жизненные показания, альтернатив нет"}).json()
    assert r["conflict"] is True and r["saved"] is True   # не блокирует, сохраняет с причиной
