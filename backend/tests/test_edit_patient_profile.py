"""Правка пациента и профиля врача."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def test_edit_patient():
    pid = c.post("/api/patients", json={"last_name": "Ошибкин", "first_name": "И"}).json()["id"]
    r = c.patch(f"/api/patients/{pid}", json={"last_name": "Иванов", "phone": "+7 900 111-22-33",
                                              "birth_date": "1980-04-05"}).json()
    assert r["last_name"] == "Иванов" and r["phone"].endswith("22-33") and r["birth_date"] == "1980-04-05"


def test_edit_doctor_profile():
    c.put("/api/settings", json={"full_name": "Петров Пётр Петрович", "specialty": "Онколог"})
    d = c.get("/api/settings").json()
    assert d["full_name"] == "Петров Пётр Петрович" and d["specialty"] == "Онколог"
