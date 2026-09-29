"""Полный справочник: препараты, классификации, перекрёстные реакции, полный МКБ,
нормализация бренд→МНН в проверке аллергий."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.reference_data import normalize_drug, drug_aliases, classifications, cross_reactions

seed.run()
c = TestClient(app)


def test_full_icd_search_non_urology():
    r = c.get("/api/reference/icd", params={"q": "E11", "scope": "full"}).json()
    assert any(x["code"].startswith("E11") for x in r["items"])   # диабет — не урология


def test_drugs_and_classifications_loaded():
    assert len(classifications()) > 0
    assert len(cross_reactions()) > 0
    r = c.get("/api/reference/drugs", params={"q": "флокс"}).json()
    assert isinstance(r["items"], list)


def test_brand_normalizes_to_inn():
    a = drug_aliases()[0]
    inn = normalize_drug(a["alias"])
    assert inn and inn != a["alias"].lower() or inn == a["normalized"]  # бренд → МНН (или уже норм.)


def test_classifications_endpoint():
    r = c.get("/api/reference/classifications").json()
    assert len(r["items"]) > 0
