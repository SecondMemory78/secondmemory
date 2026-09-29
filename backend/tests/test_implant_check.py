"""Справка по имплантам и МР-совместимости: подсказка и «что уточнить»,
НИКОГДА не допуск к МРТ и не «безопасно»."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.implant_check import mr_reference, search_devices, checklist_for, devices
seed.run()
c = TestClient(app)


def test_finds_by_article_family_and_russian_name():
    assert mr_reference("L310")["found"]          # артикул
    assert mr_reference("ACCOLADE")["found"]      # семейство латиницей
    assert mr_reference("Акколейд")["found"]      # русское написание


def test_exact_article_ranks_first():
    hits = search_devices("L310")
    assert hits and "L310" in (hits[0]["model"] or "")


def test_unknown_device_returns_nothing_not_safe():
    r = mr_reference("небывалое устройство")
    assert r["found"] is False and r["devices"] == [] and r["message"] == ""


def test_never_grants_clearance_or_says_safe():
    r = mr_reference("ACCOLADE")
    msg = r["message"].lower()
    # ключевой инвариант: не выдаём допуск, не обещаем безопасность
    assert "допуск" in msg and "не выдаёт" in msg
    for forbidden in ["можно делать мрт", "безопасно", "разрешено", "противопоказаний нет"]:
        assert forbidden not in msg


def test_records_carry_source_and_unverified_status():
    d = [x for x in devices() if x["id"] == "DEV003"][0]
    assert d["verified"] is False and d["source"]


def test_checklist_is_not_mr_status_source():
    rows = checklist_for("Кардиология")
    assert rows
    # сам лист подчёркивает: категория не определяет MR-статус
    assert any("не определяет" in (r["mr_note"] or "").lower() for r in rows)


def test_endpoints():
    r = c.get("/api/reference/implants", params={"q": "LUX-Dx"}).json()
    assert r["found"] and r["devices"][0]["mr_status"]
    cl = c.get("/api/reference/implants/checklist", params={"area": "Кардиология"}).json()
    assert len(cl["items"]) >= 1


def test_short_query_returns_nothing():
    assert search_devices("a") == []


# ── подсказка «что спросить» ────────────────────────────────────────────────
def test_questions_found_by_spoken_words():
    """Врач говорит «кардиостимулятор», в данных — «ЭКС»."""
    from app.services.implant_check import checklist_search
    assert checklist_search("кардиостимулятор")
    assert checklist_search("дефибриллятор")
    assert checklist_search("эндопротез")


def test_questions_are_not_mr_status():
    """Это вопросы для анамнеза; сам источник подчёркивает, что категория
    устройства МР-статус не определяет."""
    from app.services.implant_check import checklist_search
    rows = checklist_search("ЭКС")
    assert rows and all("ask" in r for r in rows)
    assert any("не определяет" in (r.get("mr_note") or "").lower() for r in rows)


def test_short_or_unknown_query_returns_nothing():
    from app.services.implant_check import checklist_search
    assert checklist_search("эк") == []
    assert checklist_search("нечто несуществующее") == []


def test_questions_endpoint():
    r = c.get("/api/reference/implants/ask", params={"q": "нефростома"}).json()
    assert r["items"] and "ask" in r["items"][0]


def test_implant_can_be_saved_as_a_device():
    """Ответы со слов пациента ложатся в карту как устройство."""
    pid = c.post("/api/patients", json={"last_name": "Имплантов", "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    r = c.post(f"/api/patients/{pid}/devices",
               json={"kind": "implant", "device_label": "кардиостимулятор",
                     "note": "модель: Accolade · со слов пациента"})
    assert r.status_code == 200
    items = c.get(f"/api/patients/{pid}/devices").json()["items"]
    assert items and "со слов" in items[0]["note"]     # происхождение факта видно


def test_consent_is_not_a_safety_item():
    """Согласие 152-ФЗ — юридический документ, а не пункт блока безопасности."""
    from app.routers.clinical import SAFETY_KINDS
    assert "consent" not in SAFETY_KINDS
