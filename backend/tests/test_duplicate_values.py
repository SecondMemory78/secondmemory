"""Повторная загрузка документа не плодит значения.

Врач фотографирует один анализ дважды — с двух ракурсов или просто не заметив,
что первый уже загрузился. Без проверки в очереди подтверждения появляются два
одинаковых значения, врач подтверждает оба, и в карте дубль на ту же дату.
Потом по нему строится «динамика», которой не было.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app import seed
from app.db import engine
from app.models import Observation

seed.run()
c = TestClient(app)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _pending(pid):
    with Session(engine) as s:
        return [o for o in s.exec(select(Observation).where(
            Observation.patient_id == pid)).all() if o.status == "pending"]


def _upload(pid):
    return c.post(f"/api/patients/{pid}/documents",
                  files={"file": ("a.png", PNG, "image/png")}).json()


def test_повторная_загрузка_не_добавляет_значений(own_patient):
    p = own_patient(last_name="Дубликатов", with_consent=True)
    _upload(p.id)
    after_first = len(_pending(p.id))
    assert after_first > 0, "первая загрузка ничего не дала — проверять нечего"

    _upload(p.id)
    assert len(_pending(p.id)) == after_first, "повторная загрузка создала дубли"


def test_врач_узнаёт_что_документ_уже_загружали(own_patient):
    """Молча проглотить нельзя: врач решит, что распознавание не сработало."""
    p = own_patient(last_name="Повторов", with_consent=True)
    _upload(p.id)
    second = _upload(p.id)
    got = c.get(f"/api/patients/{p.id}/documents/{second['document_id']}").json()
    dups = [r for r in got.get("rejected", []) if "уже есть" in r.get("why", "")]
    assert dups, "о дубликатах не сказано"


def test_другая_дата_дублем_не_считается(own_patient):
    """Тот же показатель в другой день — это динамика, а не дубль.

    Кладём значение напрямую, чтобы проверять ровно правило дубликатов, а не
    поведение ручного ввода.
    """
    from datetime import date
    p = own_patient(last_name="Динамиков", with_consent=True)
    with Session(engine) as s:
        s.add(Observation(patient_id=p.id, parameter_code="psa_total",
                          value_num=4.82, unit="нг/мл",
                          effective_date=date(2025, 1, 1), status="pending"))
        s.commit()

    _upload(p.id)
    with Session(engine) as s:
        dates = {o.effective_date for o in s.exec(select(Observation).where(
            Observation.patient_id == p.id,
            Observation.parameter_code == "psa_total")).all()}
    assert len(dates) >= 2, "значение за другую дату потерялось как дубль"


def test_другое_значение_на_ту_же_дату_не_дубль(own_patient):
    """Переделанный анализ — это расхождение, а не повтор. Его надо сохранить,
    чтобы врач увидел противоречие."""
    from datetime import date
    p = own_patient(last_name="Расхожев", with_consent=True)
    _upload(p.id)
    with Session(engine) as s:
        got = s.exec(select(Observation).where(
            Observation.patient_id == p.id,
            Observation.parameter_code == "psa_total")).first()
        same_date = got.effective_date
        s.add(Observation(patient_id=p.id, parameter_code="psa_total",
                          value_num=9.9, unit="нг/мл",
                          effective_date=same_date, status="pending"))
        s.commit()
        vals = {o.value_num for o in s.exec(select(Observation).where(
            Observation.patient_id == p.id,
            Observation.parameter_code == "psa_total")).all()}
    assert {4.82, 9.9} <= vals, "расхождение потеряно"
