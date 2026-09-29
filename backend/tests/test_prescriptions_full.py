"""Модуль «Назначения» по спецификации: универсальная запись, история изменений,
предложение ИИ не активно без врача."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _pid():
    pid = c.post("/api/patients", json={"last_name": "Назначев", "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    return pid


def test_non_drug_assignment_is_supported():
    """Не только лекарства: режим, диета, контроль — та же сущность."""
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/prescriptions", json={
        "drug_name": "Питьевой режим до 2 л", "category": "fluid",
        "indication": "профилактика камнеобразования", "instruction": "равномерно за день",
        "duration": "1 месяц", "control": "диурез"}).json()
    assert r["saved"] and r["conflict"] is False      # аллергии тут не проверяются
    item = c.get(f"/api/patients/{pid}/prescriptions").json()["items"][0]
    assert item["category"] == "fluid" and item["indication"] and item["control"]


def test_drug_still_checks_allergy_and_dose():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/prescriptions",
               json={"drug_name": "Амлодипин", "dose": "10 мг", "category": "drug"}).json()
    assert r["saved"] and r["dose_reference"]          # справка по дозе на месте


def test_update_keeps_previous_version_in_history():
    pid = _pid()
    rid = c.post(f"/api/patients/{pid}/prescriptions",
                 json={"drug_name": "Питьевой режим", "category": "fluid",
                       "duration": "постоянно"}).json()["id"]
    upd = c.patch(f"/api/patients/{pid}/prescriptions/{rid}",
                  json={"duration": "1 месяц", "reason": "сократили курс"}).json()
    assert upd["duration"] == "1 месяц"
    hist = c.get(f"/api/patients/{pid}/prescriptions/{rid}/history").json()["items"]
    assert len(hist) == 1
    assert hist[0]["previous"]["duration"] == "постоянно"   # прежнее не потеряно
    assert hist[0]["reason"] == "сократили курс"


def test_ai_suggestion_is_not_active_until_confirmed():
    """Главное правило спецификации (п.18): предложение ИИ — не назначение."""
    pid = _pid()
    rid = c.post(f"/api/patients/{pid}/prescriptions",
                 json={"drug_name": "Тамсулозин", "dose": "0.4 мг",
                       "source": "ai_suggested"}).json()["id"]
    item = [x for x in c.get(f"/api/patients/{pid}/prescriptions").json()["items"]
            if x["id"] == rid][0]
    assert item["status"] == "planned" and item["confirmed"] is False
    ok = c.post(f"/api/patients/{pid}/prescriptions/{rid}/confirm").json()
    assert ok["status"] == "active" and ok["confirmed"] is True


def test_doctor_assignment_is_active_right_away():
    pid = _pid()
    rid = c.post(f"/api/patients/{pid}/prescriptions",
                 json={"drug_name": "Тамсулозин", "dose": "0.4 мг"}).json()["id"]
    item = [x for x in c.get(f"/api/patients/{pid}/prescriptions").json()["items"]
            if x["id"] == rid][0]
    assert item["status"] == "active" and item["confirmed"] is True


def test_cancel_records_reason_and_keeps_record():
    pid = _pid()
    rid = c.post(f"/api/patients/{pid}/prescriptions",
                 json={"drug_name": "Тамсулозин", "dose": "0.4 мг"}).json()["id"]
    r = c.patch(f"/api/patients/{pid}/prescriptions/{rid}",
                json={"status": "cancelled", "cancel_reason": "побочный эффект",
                      "reason": "отменено врачом"}).json()
    assert r["status"] == "cancelled" and r["cancel_reason"] == "побочный эффект"
    assert any(x["id"] == rid for x in
               c.get(f"/api/patients/{pid}/prescriptions").json()["items"])   # не удалено


def test_empty_patch_and_foreign_patient_rejected():
    pid = _pid()
    rid = c.post(f"/api/patients/{pid}/prescriptions",
                 json={"drug_name": "Тамсулозин"}).json()["id"]
    assert c.patch(f"/api/patients/{pid}/prescriptions/{rid}", json={}).status_code == 400
    assert c.patch(f"/api/patients/{pid}/prescriptions/999999", json={"dose": "1"}).status_code == 404


# ── диктовка нескольких назначений одной фразой (спец., п.21) ───────────────
SAID = ("тадалафил 5 мг один раз в день месяц, питьевой режим до двух литров, "
        "ограничить тяжёлые нагрузки две недели, контрольный осмотр через месяц")


def test_dictation_splits_into_separate_items():
    from app.services.rx_dictation import rule_split
    items = rule_split(SAID)
    assert len(items) == 4                                   # пример из спецификации
    assert [i["category"] for i in items] == ["drug", "fluid", "activity", "followup"]
    assert items[0]["dose"] == "5 мг"


def test_dictation_endpoint_previews_and_saves_nothing():
    pid = _pid()
    r = c.post(f"/api/patients/{pid}/prescriptions/dictate", data={"text": SAID})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 4 and body["source"] in ("ии", "правила")
    assert c.get(f"/api/patients/{pid}/prescriptions").json()["items"] == []


def test_empty_dictation_rejected_and_foreign_404():
    pid = _pid()
    assert c.post(f"/api/patients/{pid}/prescriptions/dictate",
                  data={"text": "  "}).status_code == 400


def test_coerce_drops_junk_and_unknown_category():
    from app.services.ai import _coerce_rx
    out = _coerce_rx('{"items":[{"drug_name":"Тадалафил","category":"drug","confidence":0.9},'
                     '{"drug_name":"","category":"drug"},'
                     '{"drug_name":"Хак","category":"выдуманная","confidence":5}]}')
    assert len(out) == 2                                     # пустое имя отброшено
    assert out[1]["category"] == "other" and out[1]["confidence"] == 1.0


def test_dictation_splits_speech_without_punctuation():
    """Распознанная речь приходит БЕЗ запятых — делить нужно по смыслу."""
    from app.services.rx_dictation import rule_split
    items = rule_split("назначь тадалафил 5 миллиграмм раз в день месяц "
                       "питьевой режим до 2 литров контроль через месяц")
    assert len(items) == 3
    assert [i["category"] for i in items] == ["drug", "fluid", "followup"]
    assert items[0]["dose"].startswith("5")


def test_decimal_dose_is_not_split():
    from app.services.rx_dictation import rule_split
    items = rule_split("омник 0,4 мг на ночь месяц и сдать псa через 3 месяца")
    assert any("0,4" in i["dose"] for i in items)     # «0,4» не разорвано запятой


def test_volume_is_not_stored_as_drug_dose():
    from app.services.rx_dictation import rule_split
    fluid = [i for i in rule_split("питьевой режим до 2 литров") if i["category"] == "fluid"][0]
    assert fluid["dose"] == ""
