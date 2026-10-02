"""Барьер подписки не должен срабатывать у оплатившего врача.

На сервере ловили 402 при живой подписке: то падало, то нет, и проходило
после перезапуска службы. Причина не в «плавающем did», как предполагал
баг-репорт, а в том, что барьер открывал сессию БЕЗ контекста изоляции.
Подключения берутся из пула, и параметр app.current_doctor_id оставался на
подключении от прошлого запроса — барьер искал подписку под чужим врачом.

Ложный 402 блокирует работу оплатившего врача, поэтому проверяем и сам
механизм, и то, что контекст ставится.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import AppSession, engine
from app.deps import set_current_doctor_id, _doctor_id
from app.models import Doctor
from app.services.billing import apply_payment, subscription_ok

seed.run()
c = TestClient(app)


def test_сессия_ставит_контекст_изоляции(monkeypatch):
    """Главное: сессия сама выставляет врача на подключении."""
    seen = []
    from app.services import rls
    monkeypatch.setattr(rls, "set_session_scope",
                        lambda session, did, bypass=False: seen.append((did, bypass)))
    set_current_doctor_id(7)
    with AppSession():
        pass
    assert seen and seen[-1][0] == 7, "контекст врача не выставлен"
    assert seen[-1][1] is False


def test_без_врача_в_контексте_сессия_работает_по_всем(monkeypatch):
    """Фоновым задачам нужны все врачи — там контекста запроса нет."""
    seen = []
    from app.services import rls
    monkeypatch.setattr(rls, "set_session_scope",
                        lambda session, did, bypass=False: seen.append((did, bypass)))
    _doctor_id.set(None)
    with AppSession():
        pass
    assert seen[-1][1] is True, "без врача должен быть общий доступ"


def test_явный_врач_переопределяет_контекст(monkeypatch):
    seen = []
    from app.services import rls
    monkeypatch.setattr(rls, "set_session_scope",
                        lambda session, did, bypass=False: seen.append((did, bypass)))
    set_current_doctor_id(1)
    with AppSession(scope_doctor_id=42):
        pass
    assert seen[-1][0] == 42


def test_оплативший_врач_не_получает_402():
    with Session(engine) as s:
        d = s.exec(select(Doctor)).first()
        apply_payment(s, d.id, "12m", payment_id="gate-test")
        assert subscription_ok(s, d.id) is True

    set_current_doctor_id(1)
    r = c.post("/api/onboarding/tips/seen", json={"key": "tip:help"})
    assert r.status_code != 402, "барьер сработал у оплатившего врача"


def test_барьер_не_трогает_чтение():
    assert c.get("/api/patients").status_code == 200
