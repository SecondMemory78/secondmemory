"""Журнал ИИ: по любому значению в карте восстанавливается цепочка.

ТЗ требует, чтобы в логе были источник, результат извлечения, версия модели
или правила и последующее подтверждение либо исправление. Раньше журнал писал
только намерение и текст команды — ответить на вопрос «почему в карте это
значение» по нему было нельзя.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import AssistantAction, Observation
from app.services.ai_journal import chain, mark_outcome, CONFIRMED

seed.run()
c = TestClient(app)


def _pid():
    return c.get("/api/patients").json()[0]["id"]


def _last_action():
    with Session(engine) as s:
        return s.exec(select(AssistantAction)).all()[-1]


def test_журнал_пишет_чем_разобрано():
    c.post("/api/assistant/command", json={"text": "напомни завтра позвонить в лабораторию"})
    a = _last_action()
    assert a.engine == "rules"
    assert a.engine_version.startswith("rules-"), "версия правил не записана"


def test_цепочка_от_команды_до_подтверждения():
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    r = c.post("/api/assistant/command", json={"text": f"у {name} ПСА 7,2"}).json()
    assert r["intent"] == "observation"
    oid = r["observation_ids"][0]

    # до решения врача — предложение висит
    with Session(engine) as s:
        link = chain(s, "observation", oid)
        assert link, "действие ассистента не связалось со значением"
        assert link[-1]["outcome"] == "ожидает решения врача"
        assert link[-1]["engine"] == "rules"

    # врач подтверждает
    assert c.post(f"/api/observations/{oid}/confirm").status_code == 200
    with Session(engine) as s:
        link = chain(s, "observation", oid)
        assert link[-1]["outcome"] == CONFIRMED
        assert link[-1]["outcome_at"]


def test_происхождение_значения_отвечает_на_вопрос_почему():
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    oid = c.post("/api/assistant/command",
                 json={"text": f"у {name} креатинин 118"}).json()["observation_ids"][0]
    c.post(f"/api/observations/{oid}/confirm")

    r = c.get(f"/api/observations/{oid}/origin")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["machine_extracted"] is True
    assert d["provenance"] == "ai_extracted"
    assert d["confirmed_by"], "не видно, кто подтвердил"
    assert d["confirmed_at"]
    assert d["assistant"], "не видно, с чего всё началось"
    assert d["assistant"][0]["said"], "не сохранено, что сказал врач"


def test_уверенность_модели_не_подменяет_подтверждение():
    """Высокая уверенность — не основание: пока врач не нажал, значение ждёт."""
    pid = _pid()
    with Session(engine) as s:
        o = Observation(patient_id=pid, parameter_code="psa_total", value_num=9.9,
                        unit="нг/мл", status="pending", machine_extracted=True,
                        confidence=0.99)
        s.add(o); s.commit(); oid = o.id
    d = c.get(f"/api/observations/{oid}/origin").json()
    assert d["status"] == "pending"
    assert d["confidence"] == 0.99
    assert d["confirmed_by"] is None


def test_внесённое_врачом_руками_не_ломает_журнал():
    """Если предложения не было, отмечать нечего — и это не ошибка."""
    pid = _pid()
    oid = c.post(f"/api/patients/{pid}/observations",
                 json={"parameter_code": "psa_total", "value_num": 3.0,
                       "unit": "нг/мл"}).json()["id"]
    with Session(engine) as s:
        assert mark_outcome(s, "observation", oid, CONFIRMED) == 0
        assert chain(s, "observation", oid) == []
    d = c.get(f"/api/observations/{oid}/origin").json()
    assert d["provenance"] == "doctor"
    assert d["assistant"] == []


def test_чужое_значение_не_отдаётся():
    assert c.get("/api/observations/999999/origin").status_code == 404


# ── «врач исправил» и «врач отклонил» ───────────────────────────────────────
# Раньше в журнале могло появиться только «подтвердил»: правка значения шла
# через удаление и добавление нового, и связь терялась.

def test_исправление_значения_отмечается_как_исправление():
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    oid = c.post("/api/assistant/command",
                 json={"text": f"у {name} ПСА 7,2"}).json()["observation_ids"][0]

    r = c.patch(f"/api/observations/{oid}", json={"value_num": 7.4})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        link = chain(s, "observation", oid)
        assert link[-1]["outcome"] == "edited"


def test_исправленное_считается_проверенным():
    """Врач только что смотрел на значение — второй раз подтверждать незачем."""
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    oid = c.post("/api/assistant/command",
                 json={"text": f"у {name} креатинин 101"}).json()["observation_ids"][0]
    c.patch(f"/api/observations/{oid}", json={"value_num": 103})
    with Session(engine) as s:
        o = s.get(Observation, oid)
        assert o.status == "confirmed" and o.confirmed_by == 1


def test_прежнее_значение_остаётся_в_аудите():
    from app.models import AuditEvent
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    oid = c.post("/api/assistant/command",
                 json={"text": f"у {name} ПСА 5,5"}).json()["observation_ids"][0]
    c.patch(f"/api/observations/{oid}", json={"value_num": 5.9})
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(
            AuditEvent.entity_type == "observation",
            AuditEvent.entity_id == oid,
            AuditEvent.action == "edit")).first()
        assert ev and "было" in ev.detail and "стало" in ev.detail


def test_отклонение_отмечается_как_отклонение():
    pid = _pid()
    name = c.get(f"/api/patients/{pid}").json()["last_name"]
    oid = c.post("/api/assistant/command",
                 json={"text": f"у {name} ПСА 9,1"}).json()["observation_ids"][0]
    c.post(f"/api/observations/{oid}/reject")
    with Session(engine) as s:
        assert chain(s, "observation", oid)[-1]["outcome"] == "rejected"
