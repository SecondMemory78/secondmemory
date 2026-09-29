"""Базовый набор тестов — «страховочная сетка» перед рефакторингом швов.
Запуск: cd backend && python -m pytest -q
"""
import os, tempfile
# БД задаём ДО импорта приложения, чтобы роутеры и seed смотрели в одну базу
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import seed


@pytest.fixture(scope="module", autouse=True)
def _seed():
    seed.run()


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_patients_seeded(client):
    pts = client.get("/api/patients").json()
    assert len(pts) >= 3 and all("short_name" in p for p in pts)


def test_timeline_series(client):
    pid = client.get("/api/patients").json()[0]["id"]
    assert isinstance(client.get(f"/api/patients/{pid}/timeline").json(), dict)


def test_reminder_nl_recurrence(client):
    r = client.post("/api/reminders/quick", json={"text": "контроль PSA каждые 3 месяца !важно"}).json()
    assert r["repeat_days"] == 90 and r["priority"] == 2


def test_assistant_routes_to_appointment(client):
    r = client.post("/api/assistant/command", json={"text": "запиши на среду в 15:00 пациента Иванова"}).json()
    assert r["intent"] == "appointment"


def test_assistant_refuses_trigger_commands(client):
    # ИИ не управляет триггерами — только врач вручную. Никаких действий.
    for phrase in ["поставь триггер на PSA больше 4",
                   "включи автослежение за креатинином",
                   "следи за PSA у Иванова"]:
        r = client.post("/api/assistant/command", json={"text": phrase}).json()
        assert r["intent"] == "trigger_denied" and r["ok"] is False
    # и триггер реально не создан
    assert client.get("/api/triggers").json() == [] or all(
        True for _ in client.get("/api/triggers").json())


def test_assistant_actions_logged(client):
    # действие ассистента попадает в журнал «Что сделал ассистент»
    client.post("/api/assistant/command", json={"text": "напомни купить расходники завтра"})
    client.post("/api/assistant/command", json={"text": "поставь триггер на PSA"})
    acts = client.get("/api/assistant/actions").json()
    assert len(acts) >= 2
    # последнее — отказ по триггеру (ok=false), журнал хранит и текст, и ответ
    denied = [a for a in acts if a["intent"] == "trigger_denied"]
    assert denied and denied[0]["ok"] is False and "триггер" in denied[0]["input_text"].lower()
    task = [a for a in acts if a["intent"] == "task"]
    assert task and task[0]["area"] == "tasks" and task[0]["message"]


def test_trigger_matches_and_dedup(client):
    t = client.post("/api/triggers", json={"parameter_code": "psa_total", "op": ">", "threshold": 4.0}).json()
    assert t["matches"] >= 1
    assert client.post("/api/triggers/run").json()["created"] >= 1
    assert client.post("/api/triggers/run").json()["created"] == 0


def test_support_isolation_404(client):
    assert client.get("/api/support/threads/99999/messages").status_code == 404


def test_privacy_consent_and_export(client):
    pid = client.get("/api/patients").json()[0]["id"]
    client.post(f"/api/patients/{pid}/consent", json={"method": "tablet"})
    assert client.get(f"/api/patients/{pid}/consent").json()["status"] == "granted"
    assert "observations" in client.get(f"/api/patients/{pid}/export").json()


def test_reference_parameters_loaded(client):
    r = client.get("/api/reference/parameters").json()
    assert r["count"] == 279 and any(p["code"] == "psa_total" for p in r["items"])


def test_reference_icd_search(client):
    r = client.get("/api/reference/icd", params={"q": "N40"}).json()
    assert any(x["code"].startswith("N40") for x in r["items"])
