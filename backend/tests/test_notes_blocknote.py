"""Заметки: заголовок, папка, чек-лист.

«Блокнот» — заметки с элементами задач, а не наоборот. Пункты чек-листа НЕ
являются задачами: иначе список просроченного забьётся пунктами без срока и
врач перестанет ему доверять.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Reminder

seed.run()
c = TestClient(app)


def _new(**kw):
    body = {"text": "текст заметки"}
    body.update(kw)
    return c.post("/api/notes/my", json=body)


def test_заголовок_сохраняется():
    r = _new(title="Заказать стенты", text="позвонить поставщику")
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Заказать стенты"


def test_без_заголовка_берётся_первая_строка():
    """Список без названий через месяц превращается в стену текста."""
    r = _new(title="", text="Спросить у Петрова про анализы\nи ещё перезвонить")
    assert r.json()["title"] == "Спросить у Петрова про анализы"


def test_правка_текста_не_ломает_название():
    nid = _new(title="Моё название", text="раз").json()["id"]
    r = c.patch(f"/api/notes/my/{nid}", json={"title": "Моё название", "text": "два"})
    assert r.json()["title"] == "Моё название"


def test_заметка_может_быть_одним_списком():
    """Чек-лист без текста — нормальная заметка, а не пустая."""
    r = _new(text="", title="", checklist=[{"text": "позвонить", "done": False}])
    assert r.status_code == 200, r.text
    assert r.json()["checklist_total"] == 1


def test_совсем_пустая_не_создаётся():
    assert _new(text="", title="", checklist=[]).status_code == 400


def test_пункты_списка_не_становятся_задачами():
    """Иначе просроченное забьётся пунктами без срока."""
    with Session(engine) as s:
        before = len(s.exec(select(Reminder)).all())
    _new(checklist=[{"text": "спросить про анализы", "done": False},
                    {"text": "заказать стенты", "done": False}])
    with Session(engine) as s:
        assert len(s.exec(select(Reminder)).all()) == before


def test_счётчик_выполненного():
    r = _new(checklist=[{"text": "раз", "done": True},
                        {"text": "два", "done": False},
                        {"text": "три", "done": True}])
    assert r.json()["checklist_done"] == 2 and r.json()["checklist_total"] == 3


def test_папки_собираются_из_заметок():
    _new(title="а", folder="Закупки")
    _new(title="б", folder="Закупки")
    _new(title="в", folder="Учёба")
    items = {x["name"]: x["count"] for x in c.get("/api/notes/my/folders").json()["items"]}
    assert items.get("Закупки", 0) >= 2
    assert items.get("Учёба", 0) >= 1


def test_чужая_заметка_не_правится():
    assert c.patch("/api/notes/my/999999", json={"text": "подмена"}).status_code == 404
