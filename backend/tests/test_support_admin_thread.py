"""Ветка поддержки открывается в админке.

На сервере `GET /api/admin/support/threads/{id}` отдавал 500 с
ObjectDeletedError: в обработчике между получением ветки и сборкой ответа
стоит commit, после которого объект по умолчанию считается устаревшим, и
чтение t.id уходит в базу повторно. Такая же ловушка в проекте срабатывала
до этого трижды — на заметках, приёмах и показателях.

Лечится не здесь, а разом: сессии приложения больше не «протухают» после
commit (AppSession в db.py). Этот тест держит поведение.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed
from app.db import engine
from app.models import SupportThread, SupportMessage

seed.run()

c = TestClient(app)
AH = {"X-Admin-Token": os.getenv("ADMIN_TOKEN", "dev-admin-token")}


def _thread_with_message():
    with Session(engine) as s:
        t = SupportThread(doctor_id=1, status="open", subject="Не приходит код")
        s.add(t); s.commit(); s.refresh(t)
        s.add(SupportMessage(doctor_id=1, thread_id=t.id, author_name="Врач",
                             from_staff=False, body="Здравствуйте, не приходит код входа"))
        s.commit()
        return t.id


def test_админ_открывает_ветку():
    tid = _thread_with_message()
    r = c.get(f"/api/admin/support/threads/{tid}", headers=AH)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"] == tid
    assert len(d["messages"]) == 1


def test_объект_переживает_commit():
    """Суть ловушки: после commit поля объекта должны читаться без похода в базу."""
    with Session(engine) as s:
        t = SupportThread(doctor_id=1, status="open", subject="Проверка commit")
        s.add(t); s.commit()
        assert t.id is not None          # раньше здесь шёл повторный SELECT
        assert t.subject == "Проверка commit"


def test_повторное_открытие_помечает_прочитанным():
    """Второй заход тоже не должен падать — там ещё один commit."""
    tid = _thread_with_message()
    assert c.get(f"/api/admin/support/threads/{tid}", headers=AH).status_code == 200
    r = c.get(f"/api/admin/support/threads/{tid}", headers=AH)
    assert r.status_code == 200, r.text
    assert r.json()["messages"][0]["read_at"] is not None
