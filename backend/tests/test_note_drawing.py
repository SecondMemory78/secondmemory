"""Рисунок в заметке.

Врачи чертят пациенту схему на бумажке, и бумажка теряется. Здесь она остаётся
в заметке, может уехать в карту и попасть в памятку, которую пациент унесёт.

Рисунок хранится картинкой: текста в нём нет, искать по нему нельзя — так и
задумано.
"""
import base64
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session
from app.main import app
from app import seed
from app.db import engine
from app.models import DoctorNote

seed.run()
c = TestClient(app)

# настоящий однопиксельный PNG
PNG = ("data:image/png;base64,"
       "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_рисунок_сохраняется():
    r = c.post("/api/notes/my", json={"title": "Схема", "text": "", "drawing": PNG})
    assert r.status_code == 200, r.text
    assert r.json()["has_drawing"] is True


def test_заметка_может_быть_одним_рисунком():
    """Начертил и ушёл — текста может не быть вовсе."""
    r = c.post("/api/notes/my", json={"title": "", "text": "", "drawing": PNG})
    assert r.status_code == 200


def test_чужой_формат_не_принимается():
    bad = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="
    assert c.post("/api/notes/my", json={"title": "x", "drawing": bad}).status_code == 400


def test_огромный_рисунок_отклоняется():
    """Полмегабайта — это уже не схема, а чья-то фотография."""
    huge = "data:image/png;base64," + "A" * (600 * 1024)
    r = c.post("/api/notes/my", json={"title": "x", "drawing": huge})
    assert r.status_code == 400
    assert "большой" in r.json()["detail"].lower()


def test_правка_без_рисунка_его_не_стирает():
    """Поправил текст — схема должна остаться."""
    n = c.post("/api/notes/my", json={"title": "Схема", "drawing": PNG}).json()
    c.patch(f"/api/notes/my/{n['id']}", json={"title": "Схема", "text": "пояснение"})
    with Session(engine) as s:
        assert s.get(DoctorNote, n["id"]).drawing == PNG


def test_рисунок_можно_стереть_явно():
    n = c.post("/api/notes/my", json={"title": "Схема", "drawing": PNG}).json()
    c.patch(f"/api/notes/my/{n['id']}", json={"title": "Схема", "text": "есть текст",
                                              "drawing": ""})
    with Session(engine) as s:
        assert s.get(DoctorNote, n["id"]).drawing == ""


def test_схема_попадает_в_памятку():
    from app.services.pdf_export import build_patient_handout
    pdf = build_patient_handout(
        {"observations": [], "prescriptions": [], "appointments": [], "devices": [],
         "drawings": [PNG]},
        doctor={"full_name": "Врач"}, patient_name="Иванов И. И.")
    assert pdf[:4] == b"%PDF"


def test_битый_рисунок_не_роняет_памятку():
    """Памятка важнее картинки: не нарисовалось — печатаем остальное."""
    from app.services.pdf_export import build_patient_handout
    pdf = build_patient_handout(
        {"observations": [], "prescriptions": [], "appointments": [], "devices": [],
         "drawings": ["data:image/png;base64,не-картинка"]},
        doctor={"full_name": "Врач"}, patient_name="Иванов И. И.")
    assert pdf[:4] == b"%PDF"
