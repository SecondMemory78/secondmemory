"""T7. OCR-разбор и названия — из словаря врача (279 параметров), не из хардкода."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.parsing import parse_lab_text
from app.reference_data import parameter_label

seed.run()
c = TestClient(app)


def test_parse_recognizes_dictionary_synonyms():
    text = "ПСА общий 4.82 нг/мл\nКреатинин 118 мкмоль/л\nIPSS 21 баллы\n09.03.2026"
    codes = {v["parameter_code"] for v in parse_lab_text(text)["values"]}
    # креатинин и IPSS раньше не были захардкожены в OCR — теперь узнаются по словарю
    assert "psa_total" in codes and "creatinine" in codes and "ipss_score" in codes


def test_label_from_dictionary():
    assert parameter_label("psa_total") == "PSA общий"
    assert parameter_label("ipss_score") == "Сумма баллов IPSS"


def test_common_parameters_endpoint():
    items = c.get("/api/reference/parameters/common").json()["items"]
    assert len(items) > 0 and all("code" in x and "name" in x for x in items)


def test_labels_endpoint_has_codes():
    labels = c.get("/api/reference/parameters/labels").json()
    assert labels.get("psa_total") == "PSA общий"


def test_parameters_meta_for_charts():
    m = c.get("/api/reference/parameters/meta").json()
    assert "psa_total" in m
    assert m["psa_total"]["unit"] and "name" in m["psa_total"]
