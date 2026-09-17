"""Шифрование чувствительных полей: в БД — шифротекст, в API — открытый текст,
поиск по фамилии работает."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
seed.run()
c = TestClient(app)


def _raw(sql, *params):
    with engine.connect() as conn:
        return conn.exec_driver_sql(sql, params).fetchall()


def test_name_stored_encrypted_but_readable():
    pid = c.post("/api/patients", json={"last_name": "Секретов", "first_name": "Иван",
                                        "phone": "+7 900 123-45-67"}).json()["id"]
    p = c.get(f"/api/patients/{pid}").json()
    assert "Секретов" in p["last_name"]                      # API — открытый текст
    raw = _raw("select last_name, phone from patient where id = ?", pid)[0]
    assert "Секретов" not in raw[0] and raw[0].startswith("gAAAA")   # БД — шифротекст
    assert "900" not in (raw[1] or "")


def test_search_by_surname_still_works():
    c.post("/api/patients", json={"last_name": "Поисков", "first_name": "П"})
    found = [p["last_name"] for p in c.get("/api/patients", params={"q": "поиск"}).json()]
    assert any("Поисков" in x for x in found)


def test_note_text_encrypted():
    pid = c.get("/api/patients").json()[0]["id"]
    c.post(f"/api/patients/{pid}/notes", params={"text": "конфиденциальная жалоба"})
    rows = _raw("select text from note")
    assert all("конфиденциальная" not in (r[0] or "") for r in rows)   # в БД зашифровано
    texts = [n["text"] for n in c.get(f"/api/patients/{pid}/notes").json()]
    assert "конфиденциальная жалоба" in texts                          # в API читается
