"""Демо не тратит платные запросы к ИИ.

Витрина открыта всем без регистрации. Если бы демо ходило в Яндекс, каждый
посетитель сайта стоил бы денег, а ограничить это лимитами нельзя — демо-врач
каждый раз новый. Поэтому в демо провайдер принудительно подменяется заглушкой.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import ai

c = TestClient(app)

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def paid(monkeypatch):
    """Считает обращения к платному провайдеру."""
    calls = []

    # Провайдера подменяем прямо в модуле: переменная окружения читается один
    # раз при импорте, а порядок импорта в общем прогоне не наш.
    monkeypatch.setattr(ai, "PROVIDER", "yandex")
    monkeypatch.setattr(ai, "YANDEX_API_KEY", "test-key")
    monkeypatch.setattr(ai, "YANDEX_FOLDER_ID", "test-folder")

    def spy(name):
        def f(*a, **kw):
            calls.append(name)
            raise RuntimeError("сеть в тестах недоступна")
        return f

    for fn in ("_yandex_ocr", "_yandex_stt", "_yandex_protocol", "_yandex_rx"):
        monkeypatch.setattr(ai, fn, spy(fn))
    return calls


def _demo_headers():
    r = c.post("/api/auth/demo")
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_демо_не_ходит_в_платный_ии(paid):
    H = _demo_headers()
    pid = c.get("/api/patients", headers=H).json()[0]["id"]

    doc = c.post(f"/api/patients/{pid}/documents", headers=H,
                 files={"file": ("a.png", PNG, "image/png")})
    assert doc.status_code == 200
    c.post(f"/api/patients/{pid}/protocol/dictate", headers=H, data={"text": "жалобы никтурия"})
    c.post(f"/api/patients/{pid}/prescriptions/dictate", headers=H, data={"text": "тамсулозин 0,4 мг"})

    assert paid == [], f"демо потратило платные вызовы: {paid}"


def test_в_демо_видно_что_это_пример(paid):
    """Заглушка отвечает одно и то же на любой файл — это должно быть написано."""
    H = _demo_headers()
    pid = c.get("/api/patients", headers=H).json()[0]["id"]
    r = c.post(f"/api/patients/{pid}/documents", headers=H,
               files={"file": ("a.png", PNG, "image/png")})
    assert "ПРИМЕР РАСПОЗНАВАНИЯ" in r.json()["recognized_text"]


def test_обычный_врач_платный_ии_использует(paid):
    """Обратная проверка: подмена не должна затронуть боевой режим."""
    from app.deps import set_current_doctor_id
    set_current_doctor_id(1, is_demo=False)
    with pytest.raises(Exception):
        ai.ocr_extract(PNG)            # дошло до Яндекса и упало на сети
    assert paid == ["_yandex_ocr"], "боевой режим перестал вызывать провайдера"
