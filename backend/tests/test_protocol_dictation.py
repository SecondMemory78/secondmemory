"""Диктовка протокола по «Структуре консультации».

Ключевые требования документа: ничего не додумывать, отсутствие данных ≠ норма,
результат разбора показать и подтвердить, молча не сохранять.
"""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.protocol_dictation import rule_split, parse
seed.run()
c = TestClient(app)

SAID = ("Жалобы: никтурия три раза за ночь, слабая струя. "
        "Анамнез заболевания: около года, обследовался в поликлинике. "
        "Диагноз ДГПЖ. Рекомендации: контроль ПСА через 3 месяца")


def _pid():
    pid = c.post("/api/patients", json={"last_name": "Протоколов", "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    return pid


def test_rule_split_routes_sections():
    out = rule_split(SAID)
    assert "никтурия" in out["complaints"]
    assert "около года" in out["anamnesis_morbi"]
    assert out["diagnosis_text"].startswith("ДГПЖ")
    assert "ПСА" in out["recommendations"]


def test_untouched_sections_stay_empty():
    """Осмотр не диктовали — «без особенностей» дописывать нельзя."""
    out = rule_split(SAID)
    assert "objective" not in out and "status_localis" not in out


def test_text_without_markers_goes_to_unsorted():
    out = rule_split("пациент рассказывал про всякое")
    assert list(out) == ["unsorted"]          # не раскладываем наугад


def test_parse_marks_origin_and_status():
    out = parse(SAID)
    assert out["source"] in ("ии", "правила")
    assert "извлечено ИИ" in out["status"]     # происхождение факта помечено
    assert out["sections"] and all("label" in s for s in out["sections"])


def test_endpoint_returns_preview_and_saves_nothing():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/protocol/dictate", data={"text": SAID})
    assert r.status_code == 200
    body = r.json()
    assert len(body["sections"]) >= 4
    prot = c.get(f"/api/patients/{pid}/protocol").json()
    assert not prot["complaints"]              # молча не сохраняем


def test_empty_dictation_rejected():
    pid = _pid()
    assert c.post(f"/api/patients/{pid}/protocol/dictate", data={"text": "   "}).status_code == 400


def test_foreign_patient_is_404():
    pid = _pid()
    c.post("/api/auth/register", json={"email": "prot_other@x.ru", "phone": "+79000006611",
                                       "password": "pass12345", "full_name": "Другой"})
    lg = c.post("/api/auth/login", json={"email": "prot_other@x.ru", "password": "pass12345",
                                         "device_id": "d"}).json()
    vf = c.post("/api/auth/verify", json={"email": "prot_other@x.ru", "code": lg["dev_code"],
                                          "device_id": "d"}).json()
    hb = {"Authorization": "Bearer " + vf["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=hb)
    assert c.post(f"/api/patients/{pid}/protocol/dictate", data={"text": SAID},
                  headers=hb).status_code == 404
