"""Согласие 152-ФЗ как барьер: без согласия приём нельзя; 3 способа; проверка бланка;
фото не хранится."""
import os, tempfile, io
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed

seed.run()
c = TestClient(app)


def _new_patient():
    return c.post("/api/patients", json={"last_name": "Тестов", "first_name": "Иван",
                                         "birth_date": "1970-05-01"}).json()["id"]


def test_new_patient_blocks_prescribe_until_consent():
    pid = _new_patient()
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is False
    r = c.post(f"/api/patients/{pid}/prescriptions", json={"drug_name": "Тамсулозин"})
    assert r.status_code == 403                       # барьер: без согласия нельзя
    # старт визита тоже заблокирован
    assert c.post(f"/api/patients/{pid}/encounters", json={}).status_code == 403


def test_electronic_consent_unblocks():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is True
    assert c.post(f"/api/patients/{pid}/prescriptions", json={"drug_name": "Тамсулозин"}).json()["saved"] is True


def test_electronic_requires_agreement():
    pid = _new_patient()
    assert c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": False}).status_code == 400


def test_paper_consent_ai_verifies_and_stores_text_not_photo():
    pid = _new_patient()
    fake = io.BytesIO(b"\xff\xd8\xff fake jpeg bytes")
    r = c.post(f"/api/patients/{pid}/consent/paper",
               files={"photo": ("blank.jpg", fake, "image/jpeg")}).json()
    assert r["consent_ok"] is True and r["verified"] is True
    assert "Тестов" in r["form_text"]                 # хранится распознанный текст…
    # …а само фото как документ НЕ создано (минимизация ПДн)
    from sqlmodel import Session, select
    from app.db import engine
    from app.models import SourceDocument
    with Session(engine) as s:
        docs = s.exec(select(SourceDocument).where(SourceDocument.patient_id == pid)).all()
    assert len(docs) == 0


def test_demo_patients_have_consent():
    pid = c.get("/api/patients").json()[0]["id"]
    assert c.get(f"/api/patients/{pid}/consent").json()["consent_ok"] is True


def test_consent_blocks_all_record_writes():
    """Без согласия нельзя вносить НИЧЕГО в карту: показатель, заметка, диагноз, протокол, документ."""
    pid = _new_patient()
    assert c.post(f"/api/patients/{pid}/observations", json={"parameter_code": "psa_total", "value_num": 5}).status_code == 403
    assert c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы"}).status_code == 403
    assert c.post(f"/api/patients/{pid}/diagnoses", json={"code": "N40.0", "title": "ДГПЖ"}).status_code == 403
    assert c.put(f"/api/patients/{pid}/protocol", json={"complaints": "x"}).status_code == 403
    # после согласия — можно
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    assert c.post(f"/api/patients/{pid}/notes", params={"text": "жалобы"}).status_code == 200


# ── подпись пальцем (ПЭП) для 152-ФЗ ─────────────────────────────────────────
_SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_signature_form_exposes_es_agreement():
    pid = _new_patient()
    r = c.get(f"/api/patients/{pid}/consent/form").json()
    assert r["es_agreement_version"] and "63-ФЗ" in r["es_agreement"]


def test_electronic_with_signature_stores_es_and_flags():
    pid = _new_patient()
    r = c.post(f"/api/patients/{pid}/consent/electronic",
               json={"agreed": True, "signature": _SIG, "es_agreement_agreed": True}).json()
    assert r["consent_ok"] is True
    st = c.get(f"/api/patients/{pid}/consent").json()
    assert st["has_signature"] is True                  # подпись сохранена…
    assert "signature" not in st                        # …но не гоняется в статусе
    assert st["es_agreement_version"]                    # версия ПЭП-соглашения зафиксирована


def test_signature_requires_es_agreement():
    pid = _new_patient()
    # подпись без принятого соглашения о простой ЭП — отказ
    assert c.post(f"/api/patients/{pid}/consent/electronic",
                  json={"agreed": True, "signature": _SIG, "es_agreement_agreed": False}
                  ).status_code == 400


def test_signature_rejects_bad_format_and_oversize():
    pid = _new_patient()
    assert c.post(f"/api/patients/{pid}/consent/electronic",
                  json={"agreed": True, "signature": "notadataurl", "es_agreement_agreed": True}
                  ).status_code == 400
    big = "data:image/png;base64," + "A" * 250_001
    assert c.post(f"/api/patients/{pid}/consent/electronic",
                  json={"agreed": True, "signature": big, "es_agreement_agreed": True}
                  ).status_code == 400


def test_electronic_without_signature_still_works():
    # обратная совместимость: старый флоу без подписи по-прежнему проходит
    pid = _new_patient()
    r = c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}).json()
    assert r["consent_ok"] is True
    st = c.get(f"/api/patients/{pid}/consent").json()
    assert st["has_signature"] is False and st["es_agreement_version"] == ""


# ── просмотр/экспорт подписи как доказательства ──────────────────────────────
def test_signature_endpoint_returns_stored_signature():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic",
          json={"agreed": True, "signature": _SIG, "es_agreement_agreed": True})
    r = c.get(f"/api/patients/{pid}/consent/signature")
    assert r.status_code == 200 and r.json()["signature"] == _SIG


def test_signature_endpoint_404_without_signature():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})  # без подписи
    assert c.get(f"/api/patients/{pid}/consent/signature").status_code == 404


def test_signature_endpoint_404_for_foreign_patient():
    """Чужой врач не должен даже узнать, что подпись есть (изоляция, как и весь остальной доступ)."""
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic",
          json={"agreed": True, "signature": _SIG, "es_agreement_agreed": True})
    c.post("/api/auth/register", json={"email": "sig_other@x.ru", "phone": "+79000009911",
                                       "password": "pass12345", "full_name": "Другой"})
    lg = c.post("/api/auth/login", json={"email": "sig_other@x.ru", "password": "pass12345", "device_id": "d"}).json()
    vf = c.post("/api/auth/verify", json={"email": "sig_other@x.ru", "code": lg["dev_code"], "device_id": "d"}).json()
    hb = {"Authorization": "Bearer " + vf["token"]}
    assert c.get(f"/api/patients/{pid}/consent/signature", headers=hb).status_code == 404


def test_consent_pdf_export_builds_with_signature():
    pid = _new_patient()
    c.post(f"/api/patients/{pid}/consent/electronic",
          json={"agreed": True, "signature": _SIG, "es_agreement_agreed": True})
    r = c.get(f"/api/patients/{pid}/consent/export.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_consent_pdf_export_404_without_consent():
    pid = _new_patient()
    assert c.get(f"/api/patients/{pid}/consent/export.pdf").status_code == 404
