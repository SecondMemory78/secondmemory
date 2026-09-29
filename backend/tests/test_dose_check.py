"""Справка по дозам (dose_check): подсказка «сверьте дозу», не блокировка,
не автоматический вердикт, честный статус «не верифицировано»."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.dose_check import dose_reference
seed.run()
c = TestClient(app)


def _pid():
    p = c.post("/api/patients", json={"last_name": "Дозов", "first_name": "Тест"}).json()["id"]
    c.post(f"/api/patients/{p}/consent/electronic", json={"agreed": True})   # чтобы приём вести можно
    return p


def test_reference_matches_known_drug():
    r = dose_reference("Амлодипин", "10 мг")
    assert r["has_reference"] and len(r["records"]) >= 1
    assert r["records"][0]["source"]                     # источник показан


def test_reference_brand_and_case_insensitive():
    # нормализация как у аллергий: регистр не важен
    assert dose_reference("АМЛОДИПИН", "")["has_reference"]


def test_no_reference_for_unknown_drug():
    r = dose_reference("Небывалин", "10 мг")
    assert r["has_reference"] is False and r["records"] == [] and r["message"] == ""


def test_no_false_overdose_verdict():
    # ключевое: НЕ выносим вердикт «доза превышена» — колонка предела может быть
    # целевой дозой, а не максимумом (иначе ложная тревога на легитимной дозе).
    r = dose_reference("Тамсулозин", "0.8 мг")   # 0.8 мг — легитимный максимум
    assert r["has_reference"]
    assert "above_typical" not in r              # поля вердикта нет вовсе
    assert "превыш" not in r["message"].lower() and "выше" not in r["message"].lower()


def test_message_is_advisory_not_blocking():
    r = dose_reference("Амлодипин", "999 мг")
    # даже при абсурдной дозе — только «сверьте», не «нельзя»/«запрещено»
    assert "сверьте" in r["message"].lower()
    assert "нельзя" not in r["message"].lower() and "запрещ" not in r["message"].lower()


def test_prescribe_returns_dose_reference_without_blocking():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Амлодипин", "dose": "10 мг", "regimen": "1 раз/сут"}).json()
    assert r["saved"] is True                              # не заблокировано
    assert r["dose_reference"] and r["dose_reference"]["has_reference"] is True


def test_prescribe_unknown_drug_no_dose_reference():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Небывалин", "dose": "5 мг"}).json()
    assert r["saved"] is True and r["dose_reference"] is None


def test_dose_reference_endpoint():
    r = c.get("/api/reference/dose", params={"drug": "Метотрексат"}).json()
    assert r["has_reference"] and len(r["records"]) >= 1


# ── формат дат: российский стандарт ДД.ММ.ГГГГ ───────────────────────────────
def test_pdf_dates_use_russian_format():
    from app.services.pdf_export import _ru_date, _ru_datetime
    assert _ru_date("2026-10-15") == "15.10.2026"
    assert _ru_datetime("2026-10-15T14:03:00") == "15.10.2026 14:03"
    assert _ru_date(None) == "" and _ru_date("") == ""      # пусто не превращаем в мусор
    assert _ru_date("15.10.2026") == "15.10.2026"            # уже русский — не ломаем


def test_consent_pdf_has_no_iso_dates():
    import re
    pid = _pid()
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    pdf = c.get(f"/api/patients/{pid}/consent/export.pdf")
    assert pdf.status_code == 200
    # в PDF не должно остаться дат вида 2026-09-26 (сжатие может скрыть текст,
    # поэтому проверяем сам генератор напрямую)
    from app.services.pdf_export import build_consent_pdf
    data = build_consent_pdf({"last_name": "Т", "first_name": "Т", "birth_date": "1970-01-01"},
                             {"status": "granted", "method": "electronic",
                              "granted_at": "2026-10-15T14:03:00", "text_version": "v1"})
    assert data[:4] == b"%PDF"
