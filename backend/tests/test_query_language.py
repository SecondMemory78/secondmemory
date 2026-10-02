"""Вопросы к картотеке на обычном языке.

Главное правило: модель не отвечает и не пишет запрос к базе — она переводит
вопрос в условия из утверждённого словаря, а поиск выполняет наш код. Поэтому
проверяем именно разбор вопроса и отбор, а не формулировку ответа.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date, timedelta
from sqlmodel import Session, select
from app import seed, clock
from app.db import engine
from app.models import Patient, Device, Observation, Reminder, Prescription
from app.deps import set_current_doctor_id
from app.services.query import ask, parse_question, validate, looks_like_question

seed.run()
set_current_doctor_id(1)


def _setup():
    with Session(engine) as s:
        a, b, c = s.exec(select(Patient)).all()[:3]
        wk0, _ = clock.week_bounds()
        s.add(Device(doctor_id=1, patient_id=a.id, kind="stent", side="right", active=True,
                     installed_at=date.today() - timedelta(days=30), due_at=wk0 + timedelta(days=9)))
        s.add(Device(doctor_id=1, patient_id=b.id, kind="nephrostomy", active=True,
                     installed_at=date.today() - timedelta(days=10)))
        s.add(Observation(patient_id=c.id, parameter_code="psa_total", value_num=12.4,
                          unit="нг/мл", effective_date=date.today(), status="confirmed"))
        s.add(Reminder(doctor_id=1, patient_id=b.id, title="Контроль креатинина",
                       parameter_code="creatinine", status="open",
                       due_at=clock.now() - timedelta(days=3)))
        s.add(Prescription(patient_id=c.id, drug_name="Биопсия простаты",
                           category="procedure", instruction="Биопсия простаты",
                           status="planned"))
        s.commit()
        return a.id, b.id, c.id


A, B, C = _setup()


def _ask(q):
    with Session(engine) as s:
        return ask(s, q)


def _ids(r):
    return {i["patient_id"] for i in r["items"]}


# ── примеры из ТЗ ───────────────────────────────────────────────────────────

def test_стенты_на_следующей_неделе():
    r = _ask("Кому нужно убрать стенты на следующей неделе?")
    assert _ids(r) == {A}


def test_у_кого_нефростомы():
    r = _ask("У каких пациентов сейчас стоят нефростомы?")
    assert _ids(r) == {B}
    # у пациента со стентом нефростомы нет — он попасть не должен
    assert A not in _ids(r)


def test_контроль_креатинина_не_выполнен():
    r = _ask("Кому назначен контроль креатинина и он не выполнен?")
    assert _ids(r) == {B}


def test_пса_выше_порога():
    r = _ask("У кого ПСА > 10 нг/мл?")
    assert _ids(r) == {C}
    assert "psa_total" in r["explain"]


def test_ожидают_биопсию_падеж_не_мешает():
    """В вопросе «биопсию», в назначении «Биопсия» — сравниваем по основе."""
    assert _ids(_ask("Какие пациенты ожидают биопсию простаты?")) == {C}


def test_стационар_честно_говорим_что_данных_нет():
    r = _ask("Кто сейчас находится на койке?")
    assert r["items"] == []
    assert "стационар" in r["message"].lower()


def test_вопрос_про_одного_пациента_не_отвечается_списком():
    """Врач спросил про одного — выдать всех подходящих было бы обманом."""
    for q in ("Когда этому пациенту последний раз меняли стент?",
              "Какая последняя операция у пациента?"):
        r = _ask(q)
        assert r["items"] == []
        assert "фамилию" in r["message"].lower()


# ── защита ──────────────────────────────────────────────────────────────────

def test_выдуманные_условия_отбрасываются():
    """Всё, чего нет в словаре, не доходит до базы."""
    assert validate({"device_kind": "stent", "удалить_всё": True,
                     "doctor_id": 999}) == {"device_kind": "stent"}


def test_неизвестный_тип_устройства_отбрасывается():
    assert validate({"device_kind": "ракета"}) == {}


def test_непонятый_вопрос_не_придумывает_ответ():
    r = _ask("Как дела?")
    assert r["ok"] is False and r["items"] == []


def test_вопрос_отличается_от_команды():
    assert looks_like_question("У кого ПСА выше 10?")
    assert not looks_like_question("запиши Иванова на среду 15:00")


def test_ответ_показывает_по_каким_условиям_искали():
    r = _ask("У каких пациентов стоят нефростомы?")
    assert r["explain"] and "нефростома" in r["explain"]


# ── модель как запасной вариант ─────────────────────────────────────────────
# Правила идут первыми. Модель подключается, только если они не справились, и
# её ответ проходит ту же проверку: придумать условие она не может.

def test_модель_не_зовётся_если_правила_справились(monkeypatch):
    called = []
    from app.services import ai
    monkeypatch.setattr(ai, "parse_query", lambda t: called.append(t) or {})
    parse_question("У кого ПСА > 10?")
    assert called == [], "правила поняли вопрос, модель дёргать незачем"


def test_модель_подключается_когда_правила_молчат(monkeypatch):
    from app.services import ai
    monkeypatch.setattr(ai, "parse_query",
                        lambda t: {"device_kind": "nephrostomy"})
    q = parse_question("а у кого там трубка в почке стоит")
    assert q.filters == {"device_kind": "nephrostomy"}


def test_выдумки_модели_отбрасываются(monkeypatch):
    """Модель вернула несуществующие поля и опасное значение — не проходит."""
    from app.services import ai
    monkeypatch.setattr(ai, "parse_query", lambda t: {
        "device_kind": "ракета",          # нет такого типа
        "drop_table": "patient",          # нет такого поля
        "doctor_id": 999,                 # чужой врач — поля нет в словаре
        "parameter_code": "psa_total",    # а это допустимо
        "value": "не число",              # не приводится
    })
    q = parse_question("непонятный вопрос про что-то")
    assert q.filters == {"parameter_code": "psa_total"}


def test_молчание_модели_не_ломает_ответ(monkeypatch):
    from app.services import ai
    monkeypatch.setattr(ai, "parse_query", lambda t: None)
    q = parse_question("как дела")
    assert q.filters == {}


def test_модель_не_зовётся_когда_данных_нет_совсем(monkeypatch):
    """«Кто на койке» — честный отказ, а не поход к модели за выдумкой."""
    called = []
    from app.services import ai
    monkeypatch.setattr(ai, "parse_query", lambda t: called.append(t) or {})
    q = parse_question("Кто сейчас находится на койке?")
    assert called == []
    assert q.unsupported
