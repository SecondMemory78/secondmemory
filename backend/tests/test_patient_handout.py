"""Памятка пациенту на руки.

Проверяем ОТБОР данных, а не картинку: текст внутри PDF закодирован
подмножеством шрифта, и проверки «есть ли такое слово в файле» проходят
впустую — первая версия этих тестов именно так и обманывала.

Правила, которые держим:
  • задачи врача в памятку не попадают — «снять катетер» пациент прочитает как
    указание себе, а в заголовке задачи может стоять чужая фамилия;
  • непроверенные значения не печатаются;
  • пустой раздел не печатается вовсе, вместо него не появляется «без
    особенностей» и прочие типовые фразы.
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.services.pdf_export import handout_sections, build_patient_handout

seed.run()
c = TestClient(app)

EMPTY = {"observations": [], "prescriptions": [], "reminders": [], "appointments": []}


def sections(**over):
    data = dict(EMPTY); data.update(over)
    return {s["key"]: s for s in handout_sections(data, when=date(2026, 9, 30))}


def test_памятка_отдаётся_pdf():
    pid = c.get("/api/patients").json()[0]["id"]
    r = c.get(f"/api/patients/{pid}/handout.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    assert "pamyatka" in r.headers.get("content-disposition", "")


def test_задачи_врача_в_памятку_не_попадают():
    s = sections(reminders=[{"title": "Снять катетер — Петрова М. Н.", "status": "open",
                             "due_at": "2026-10-01"}])
    assert s == {}, "задачи врача не должны давать ни одного раздела"


def test_непроверенные_значения_не_печатаются():
    s = sections(observations=[
        {"parameter_code": "psa", "label": "ПСА", "value_num": 3.1, "unit": "нг/мл",
         "effective_date": "2026-01-10", "status": "confirmed"},
        {"parameter_code": "psa", "label": "ПСА", "value_num": 9.9, "unit": "нг/мл",
         "effective_date": "2026-09-01", "status": "pending"},
    ])
    # осталось одно подтверждённое значение — «было → стало» не из чего строить
    assert "changes" not in s


def test_динамика_только_из_подтверждённых():
    s = sections(observations=[
        {"parameter_code": "psa", "label": "ПСА", "value_num": 3.1, "unit": "нг/мл",
         "effective_date": "2026-01-10", "status": "confirmed"},
        {"parameter_code": "psa", "label": "ПСА", "value_num": 4.8, "unit": "нг/мл",
         "effective_date": "2026-09-01", "status": "confirmed"},
        {"parameter_code": "psa", "label": "ПСА", "value_num": 9.9, "unit": "нг/мл",
         "effective_date": "2026-09-20", "status": "pending"},
    ])
    row = s["changes"]["rows"][0]
    assert "3,1" in row[1] and "4,8" in row[1]
    assert "9,9" not in row[1]          # непроверенное не стало «стало»


def test_пустая_памятка_ничего_не_придумывает():
    assert sections() == {}
    pdf = build_patient_handout(EMPTY, doctor={"full_name": "Врач"}, patient_name="Иванов И. И.")
    assert pdf[:4] == b"%PDF"           # документ всё равно собирается


def test_лекарства_и_дела_разнесены():
    s = sections(prescriptions=[
        {"drug_name": "Тамсулозин", "category": "drug", "dose": "0,4 мг",
         "frequency": "на ночь", "duration": "1 месяц", "status": "active"},
        {"drug_name": "ПСА", "category": "lab", "instruction": "Сдать кровь на ПСА",
         "indication": "контроль", "status": "active"},
    ])
    assert s["meds"]["rows"][0][0] == "Тамсулозин"
    assert s["todo"]["rows"][0][0] == "Сдать кровь на ПСА"


def test_отменённое_и_неподтверждённое_не_печатается():
    s = sections(prescriptions=[
        {"drug_name": "Отменённый", "category": "drug", "status": "cancelled"},
        {"drug_name": "Предложено ИИ", "category": "drug", "status": "active", "confirmed": False},
    ])
    assert s == {}


def test_прошедший_приём_не_зовут():
    s = sections(appointments=[{"starts_at": "2026-09-01T10:00:00"}])
    assert "visit" not in s
    s = sections(appointments=[{"starts_at": "2026-10-05T12:30:00"},
                               {"starts_at": "2026-10-20T09:00:00"}])
    assert "05.10.2026" in s["visit"]["text"]      # зовём на ближайший


# ── правила, добавленные по ТЗ модуля «Выписка» ─────────────────────────────

def test_динамика_только_при_значимом_изменении():
    """ТЗ запрещает печатать динамику подряд по всем показателям."""
    small = sections(observations=[
        {"parameter_code": "cr", "label": "Креатинин", "value_num": 100, "unit": "мкмоль/л",
         "effective_date": "2026-01-10", "status": "confirmed"},
        {"parameter_code": "cr", "label": "Креатинин", "value_num": 104, "unit": "мкмоль/л",
         "effective_date": "2026-09-01", "status": "confirmed"},
    ])
    assert "changes" not in small          # 4% — колебание, пациенту не нужно

    big = sections(observations=[
        {"parameter_code": "psa", "label": "ПСА", "value_num": 3.1, "unit": "нг/мл",
         "effective_date": "2026-01-10", "status": "confirmed"},
        {"parameter_code": "psa", "label": "ПСА", "value_num": 4.8, "unit": "нг/мл",
         "effective_date": "2026-09-01", "status": "confirmed"},
    ])
    assert "changes" in big                # выросло на 55% — печатаем


def test_отмеченный_врачом_показатель_печатается_всегда():
    s = sections(observations=[
        {"parameter_code": "cr", "label": "Креатинин", "value_num": 100, "unit": "мкмоль/л",
         "effective_date": "2026-01-10", "status": "confirmed"},
        {"parameter_code": "cr", "label": "Креатинин", "value_num": 102, "unit": "мкмоль/л",
         "effective_date": "2026-09-01", "status": "confirmed", "for_handout": True},
    ])
    assert "changes" in s


def test_активные_устройства_в_памятке():
    s = sections(devices=[
        {"kind": "stent", "device_label": "справа", "active": True,
         "installed_at": "2026-09-10", "due_at": "2026-11-09"},
        {"kind": "catheter", "active": False, "installed_at": "2026-01-01"},
    ])
    rows = s["devices"]["rows"]
    assert len(rows) == 1                          # снятое устройство не печатаем
    assert "справа" in rows[0][0]
    assert "09.11.2026" in rows[0][2]


def test_срочные_признаки_только_по_своим_устройствам():
    s = sections(devices=[{"kind": "nephrostomy", "active": True}])
    text = " ".join(s["urgent"]["bullets"])
    assert "нефростоме" in text
    assert "катетер" not in text                   # универсального списка быть не должно
    assert sections(devices=[]) == {}              # устройств нет — блока нет


def test_предупреждение_врачу_про_срок():
    from app.services.pdf_export import handout_warnings
    w = handout_warnings({"devices": [
        {"kind": "nephrostomy", "active": True, "installed_at": "2026-09-25", "due_at": None}]})
    assert any("срок" in x for x in w)
    ok = handout_warnings({"devices": [
        {"kind": "stent", "active": True, "installed_at": "2026-09-10", "due_at": "2026-11-09"}]})
    assert ok == []


def test_рекомендации_отделены_от_обследований():
    s = sections(prescriptions=[
        {"drug_name": "ПСА", "category": "lab", "instruction": "Сдать кровь на ПСА", "status": "active"},
        {"drug_name": "Режим", "category": "activity", "instruction": "Не поднимать тяжести", "status": "active"},
    ])
    assert s["todo"]["rows"][0][0] == "Сдать кровь на ПСА"
    assert any("тяжести" in b for b in s["recs"]["bullets"])
