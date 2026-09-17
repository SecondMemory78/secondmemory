"""Задача 3: фото с несколькими пациентами — разбивка, приватность, идемпотентность."""
import os, tempfile, io, json
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)
H = {"Authorization": "Bearer " + __import__("json").loads(TestClient(app).post("/api/auth/demo").content)["token"]}


def _consented(last):
    pid = c.post("/api/patients", headers=H, json={"last_name": last, "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True}, headers=H)
    return pid


def _upload(sim, key=""):
    hh = dict(H)
    if key:
        hh["idempotency-key"] = key
    return c.post("/api/intake/photo-batch", headers=hh,
                  data={"sim": json.dumps(sim)},
                  files={"file": ("list.jpg", io.BytesIO(b"img"), "image/jpeg")})


def test_split_into_fragments_and_identity():
    pa = _consented("Фотин")   # существующий пациент → фрагмент должен его узнать
    sim = [{"last_name": "Фотин", "first_name": "Т", "values": [{"parameter_code": "psa_total", "value_num": 5.0, "unit": "нг/мл"}]},
           {"last_name": "Незнамов", "first_name": "Н"}]   # второго нет в базе → new
    b = _upload(sim).json()
    assert len(b["fragments"]) == 2
    f0 = b["fragments"][0]
    assert f0["identity"]["action"] == "use"            # Фотин узнан
    assert b["fragments"][1]["identity"]["action"] == "new"


def test_privacy_fragment_goes_only_to_its_patient():
    pa = _consented("Приватьев")
    pb = _consented("Соседов")
    sim = [{"last_name": "Приватьев", "first_name": "Т", "values": [{"parameter_code": "psa_total", "value_num": 3.3, "unit": "нг/мл"}]},
           {"last_name": "Соседов", "first_name": "Т", "values": [{"parameter_code": "psa_total", "value_num": 9.9, "unit": "нг/мл"}]}]
    b = _upload(sim).json()
    # назначаем фрагменты правильным пациентам
    for f in b["fragments"]:
        target = pa if "Приватьев" in f["extracted_name"] else pb
        c.post(f"/api/intake/photo-batch/{b['id']}/fragment/{f['id']}/assign", headers=H, json={"patient_id": target})
    r = c.post(f"/api/intake/photo-batch/{b['id']}/confirm", headers=H).json()
    assert len(r["committed"]) == 2 and r["image_deleted"] is True
    # у Приватьева только его значение (3.3), значения соседа (9.9) в его карте НЕТ
    tl_a = c.get(f"/api/patients/{pa}/timeline", headers=H).json()
    vals_a = [x["value_num"] for x in tl_a.get("psa_total", [])]
    assert 3.3 in vals_a and 9.9 not in vals_a
    tl_b = c.get(f"/api/patients/{pb}/timeline", headers=H).json()
    vals_b = [x["value_num"] for x in tl_b.get("psa_total", [])]
    assert 9.9 in vals_b and 3.3 not in vals_b


def test_image_deleted_after_confirm():
    pa = _consented("Удалихин")
    b = _upload([{"last_name": "Удалихин", "first_name": "Т"}]).json()
    assert c.get(f"/api/intake/photo-batch/{b['id']}", headers=H).json()["has_image"] is True
    f = b["fragments"][0]
    c.post(f"/api/intake/photo-batch/{b['id']}/fragment/{f['id']}/assign", headers=H, json={"patient_id": pa})
    c.post(f"/api/intake/photo-batch/{b['id']}/confirm", headers=H)
    assert c.get(f"/api/intake/photo-batch/{b['id']}", headers=H).json()["has_image"] is False


def test_idempotent_upload():
    b1 = _upload([{"last_name": "Идемпотов", "first_name": "Т"}], key="abc-123").json()
    b2 = _upload([{"last_name": "Идемпотов", "first_name": "Т"}], key="abc-123").json()
    assert b1["id"] == b2["id"]                          # повтор не создал новый пакет


def test_cannot_assign_foreign_patient():
    # регистрируем второго врача и его пациента
    c.post("/api/auth/register", json={"email": "d2@x.ru", "phone": "+79991112233", "password": "pass12345", "full_name": "Д2"})
    r = c.post("/api/auth/login", json={"email": "d2@x.ru", "password": "pass12345", "device_id": "d"}).json()
    v = c.post("/api/auth/verify", json={"email": "d2@x.ru", "code": r["dev_code"], "device_id": "d"}).json()
    H2 = {"Authorization": "Bearer " + v["token"]}
    c.post("/api/billing/subscribe", json={"plan": "1m"}, headers=H2)
    foreign = c.post("/api/patients", headers=H2, json={"last_name": "Чужой", "first_name": "Т"}).json()["id"]
    # наш врач грузит пакет и пытается назначить фрагмент чужому пациенту
    b = _upload([{"last_name": "Ктотов", "first_name": "Т"}]).json()
    f = b["fragments"][0]
    rr = c.post(f"/api/intake/photo-batch/{b['id']}/fragment/{f['id']}/assign", headers=H, json={"patient_id": foreign})
    assert rr.status_code == 404                         # чужого пациента назначить нельзя
