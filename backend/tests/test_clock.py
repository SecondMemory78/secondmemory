"""T3. Дашборд и seed работают относительно НАСТОЯЩЕГО сегодня, без хардкода 2026-03-12."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import date
from fastapi.testclient import TestClient
from app.main import app
from app import seed, clock

seed.run()
c = TestClient(app)


def test_clock_today_is_real():
    assert clock.today() == date.today() or abs((clock.today() - date.today()).days) <= 1


def test_dashboard_date_is_today_not_hardcoded():
    d = c.get("/api/dashboard").json()
    assert d["date"] == clock.today().isoformat()
    assert d["date"] != "2026-03-12"


def test_dashboard_today_has_appointments():
    # seed кладёт приёмы на сегодня → дашборд должен их видеть
    assert c.get("/api/dashboard").json()["today_appointments"] >= 1


def test_weekly_counts_current_week():
    assert c.get("/api/dashboard").json()["weekly"]["appointments"] >= 1
