"""Настройки врача сохраняются (не только локально)."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def test_settings_roundtrip():
    d = c.get("/api/settings").json()
    assert "notify_push" in d and "notify_tracking" in d
    c.put("/api/settings", json={"notify_push": False})
    assert c.get("/api/settings").json()["notify_push"] is False
    c.put("/api/settings", json={"notify_push": True})
    assert c.get("/api/settings").json()["notify_push"] is True
