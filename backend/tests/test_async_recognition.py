"""Распознавание документа идёт фоном.

Раньше врач ждал ответа провайдера прямо во время приёма — с телефоном в руке,
при пациенте. Теперь фотография принимается сразу, а значения доезжают в
очередь подтверждения.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import SourceDocument, Observation

seed.run()
c = TestClient(app)
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def test_загрузка_отвечает_сразу():
    r = c.post(f"/api/patients/{_pid()}/documents",
               files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["document_id"]
    assert d["ocr_status"] == "queued"
    assert "продолж" in d["message"].lower() or "появятся" in d["message"].lower()


def test_результат_доезжает_и_его_видно():
    pid = _pid()
    doc_id = c.post(f"/api/patients/{pid}/documents",
                    files={"file": ("a.png", PNG, "image/png")}).json()["document_id"]
    got = c.get(f"/api/patients/{pid}/documents/{doc_id}").json()
    assert got["ocr_status"] == "done"
    assert got["recognized_text"]
    # фото не хранится — только текст
    assert got["image_purged"] is True


def test_значения_попадают_на_подтверждение(own_patient):
    # Свой пациент: в этом файле документ грузится несколько раз, а повторная
    # загрузка теперь справедливо считается дубликатом и значений не создаёт.
    pid = own_patient(last_name="Распознаев", with_consent=True).id
    doc_id = c.post(f"/api/patients/{pid}/documents",
                    files={"file": ("a.png", PNG, "image/png")}).json()["document_id"]
    with Session(engine) as s:
        vals = s.exec(select(Observation).where(
            Observation.source_document_id == doc_id)).all()
        assert vals, "распознанные значения не создались"
        for o in vals:
            assert o.status == "pending"          # в карту без врача не идут
            assert o.machine_extracted is True
            assert o.provenance == "document"


def test_чужой_документ_не_отдаётся():
    pid = _pid()
    assert c.get(f"/api/patients/{pid}/documents/999999").status_code == 404


def test_падение_распознавания_помечается(monkeypatch):
    """Ошибка не должна теряться: врач увидит «не удалось», а не пустоту."""
    from app.routers import intake
    monkeypatch.setattr(intake, "extract_values",
                        lambda b: (_ for _ in ()).throw(RuntimeError("провайдер молчит")))
    pid = _pid()
    doc_id = c.post(f"/api/patients/{pid}/documents",
                    files={"file": ("b.png", PNG, "image/png")}).json()["document_id"]
    got = c.get(f"/api/patients/{pid}/documents/{doc_id}").json()
    assert got["ocr_status"] == "failed"
    assert "не удалось" in got["recognized_text"].lower()
