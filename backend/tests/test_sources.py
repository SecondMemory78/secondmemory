"""Поиск по доверенным источникам: обезличивание, доверие ссылке, честность.

Правила врача: только цитата и ссылка, никаких выводов ИИ; кеш общий и
обезличенный; нет проверки — пишем «не проверено», ничего не выдумываем.
"""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed, clock
from app.db import engine
from app.models import SourceLookup
from app.services import sources as S
seed.run()
c = TestClient(app)
AH = {"x-admin-token": "dev-admin-token"}
GRLS = "https://grls.rosminzdrav.ru/GRLS.aspx"


# ── обезличивание ───────────────────────────────────────────────────────────
STEMS = {"иванов", "сидоров", "петр"}          # основы фамилий пациентов врача


def test_dates_age_and_numbers_are_stripped():
    out = S.anonymize("62 года 22.01.1964 полис 1234567890 тамсулозин доза")
    assert "1964" not in out and "1234567890" not in out and "62" not in out
    assert "тамсулозин" in out


def test_patient_surnames_are_stripped_in_any_case_form():
    out = S.anonymize("Иванову Сидорова тамсулозин доза", STEMS)
    assert "Иванов" not in out and "Сидоров" not in out and "тамсулозин" in out


def test_drug_names_are_never_stripped():
    """Ключевое: «тамсулозин», «амлодипин» кончаются как фамилии. Если их
    вырезать, разные препараты дадут ОДИН ключ кеша и цитату одного покажут
    для другого — клинически опасно."""
    for drug in ("Тамсулозин", "Амлодипин", "Аллопуринол", "Небывалин"):
        assert drug.lower() in S.anonymize(f"{drug} максимальная доза", STEMS).lower()


def test_different_drugs_get_different_cache_keys():
    a = S.normalize("Небывалин максимальная суточная доза", STEMS)
    b = S.normalize("Неизвестнин максимальная суточная доза", STEMS)
    assert a != b and a and b


def test_is_anonymous_guards_the_shared_cache():
    assert S.is_anonymous("тамсулозин максимальная доза", STEMS)
    assert not S.is_anonymous("Сидорова тамсулозин", STEMS)
    assert not S.is_anonymous("тамсулозин 22.01.1964", STEMS)


# ── доверие ссылке ──────────────────────────────────────────────────────────
def test_only_trusted_domains_are_accepted():
    assert S.is_trusted(GRLS) and S.is_trusted("https://cr.minzdrav.gov.ru/clin-rec")
    assert S.is_trusted("https://www.ema.europa.eu/en/medicines")     # поддомен
    assert not S.is_trusted("https://medblog.example/statya")
    assert not S.is_trusted("не ссылка")


def test_foreign_sources_are_labelled():
    ema = S.source_for("https://www.ema.europa.eu/en/medicines")
    assert ema["scope"] == "eu"                 # не выдаём за российское
    assert S.source_for(GRLS)["scope"] == "rf"


def test_saving_untrusted_link_is_rejected():
    r = c.post("/api/admin/sources/result", headers=AH,
               json={"query": "тест", "quote": "x", "url": "https://blog.example/a"})
    assert r.status_code == 400


def test_personal_data_never_lands_in_the_shared_cache():
    """Главное свойство: как бы врач ни спросил, в общий кеш имя не попадёт."""
    c.post("/api/patients", json={"last_name": "Сидорова", "first_name": "Мария"})
    c.get("/api/reference/sources/lookup",
          params={"q": "Сидоровой Марии 22.01.1964 тамсулозин доза"})
    with Session(engine) as s:
        rows = s.exec(select(SourceLookup)).all()
    blob = " ".join(r.query for r in rows)
    assert "сидоров" not in blob.lower() and "мари" not in blob.lower() and "1964" not in blob
    assert any("тамсулозин" in r.query for r in rows)     # суть вопроса сохранилась


# ── кеш и честность ─────────────────────────────────────────────────────────
def test_first_ask_is_queued_and_says_not_checked():
    r = c.get("/api/reference/sources/lookup", params={"q": "абиратерон показания"}).json()
    assert r["status"] == "pending" and "не проверено" in r["note"].lower()
    assert r["quote"] == "" and r["url"] == ""       # ничего не выдумываем


def test_saved_answer_is_returned_with_link_and_date():
    q = "тамсулозин максимальная суточная доза"
    c.get("/api/reference/sources/lookup", params={"q": q})
    c.post("/api/admin/sources/result", headers=AH,
           json={"query": q, "quote": "Максимальная суточная доза — 0,4 мг", "url": GRLS})
    r = c.get("/api/reference/sources/lookup", params={"q": q}).json()
    assert r["status"] == "ok" and r["url"] == GRLS
    assert r["checked_at"] and r["stale"] is False
    assert "0,4" in r["quote"]


def test_cache_is_shared_via_normalised_query():
    """Тот же вопрос с именем пациента попадает в ту же запись кеша."""
    r = c.get("/api/reference/sources/lookup",
              params={"q": "Иванову тамсулозин максимальная суточная доза"}).json()
    assert r["status"] == "ok"


def test_answer_older_than_half_a_year_is_requeued():
    q = "аллопуринол показания"
    c.post("/api/admin/sources/result", headers=AH,
           json={"query": q, "quote": "текст", "url": GRLS})
    with Session(engine) as s:
        row = s.exec(select(SourceLookup).where(SourceLookup.query == q)).first()
        row.checked_at = clock.now() - timedelta(days=200)
        s.add(row); s.commit()
    r = c.get("/api/reference/sources/lookup", params={"q": q}).json()
    assert r["status"] == "pending"          # пора перепроверить


def test_sources_list_is_visible_to_the_doctor():
    items = c.get("/api/reference/sources").json()["items"]
    codes = {i["code"] for i in items}
    assert {"kr_minzdrav", "grls", "rzn_devices", "caprini"} <= codes
    eau = [i for i in items if i["code"] == "eau"][0]
    assert eau["scope_label"] == "EU"


def test_admin_queue_requires_auth():
    assert c.get("/api/admin/sources/pending").status_code == 401
