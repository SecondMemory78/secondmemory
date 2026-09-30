"""Каждая подсказка из интерфейса должна быть в белом списке сервера.

Иначе отметка «видел» отклоняется с 400, клиент молча её проглатывает, и
подсказка вылезает при каждой загрузке страницы. Ровно это и случилось с
подсказками про кнопку приёма и ассистента: во фронте добавил, на сервере — нет.
"""
import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.onboarding import TIP_KEYS

seed.run()
c = TestClient(app)

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _keys_in_frontend() -> set:
    keys = set()
    for f in list(FRONT.rglob("*.jsx")) + list(FRONT.rglob("*.js")):
        text = f.read_text(encoding="utf-8")
        keys.update(re.findall(r'["\'](tip:[a-z0-9-]+)["\']', text))
    return keys


def test_все_подсказки_интерфейса_известны_серверу():
    used = _keys_in_frontend()
    assert used, "подсказок в интерфейсе не нашлось — проверьте путь"
    unknown = sorted(used - TIP_KEYS)
    assert not unknown, f"нет в белом списке сервера: {unknown}"


def test_отметка_видел_принимается():
    for key in sorted(_keys_in_frontend()):
        r = c.post("/api/onboarding/tips/seen", json={"key": key})
        assert r.status_code == 200, f"{key} → {r.status_code}"


def test_увиденное_запоминается():
    c.post("/api/onboarding/tips/seen", json={"key": "tip:start-visit"})
    seen = c.get("/api/onboarding/progress").json()["tips_seen"]
    assert "tip:start-visit" in seen


def test_чужой_ключ_отклоняется():
    assert c.post("/api/onboarding/tips/seen", json={"key": "tip:выдуманная"}).status_code == 400
