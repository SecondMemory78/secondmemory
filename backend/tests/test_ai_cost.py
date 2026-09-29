"""Оценка стоимости расхода ИИ и алерт при превышении прогноза."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"x-admin-token": "dev-admin-token"}


def test_cost_report_shape():
    r = c.get("/api/admin/usage/cost", headers=H).json()
    assert "threshold_rub" in r and "prices" in r and "doctors" in r
    assert set(r["prices"].keys()) == {"ocr", "stt", "llm"}


def test_cost_alert_triggers_and_dedups():
    # низкий порог, чтобы демо-расход точно его превысил
    os.environ["AI_COST_ALERT_RUB"] = "1"
    try:
        n1 = c.post("/api/admin/usage/cost/check", headers=H).json()["alerts_created"]
        assert n1 >= 1                      # алерт создан
        n2 = c.post("/api/admin/usage/cost/check", headers=H).json()["alerts_created"]
        assert n2 == 0                      # повторно за месяц не дублируется
    finally:
        os.environ.pop("AI_COST_ALERT_RUB", None)


def test_cost_report_requires_admin():
    assert c.get("/api/admin/usage/cost").status_code == 401
