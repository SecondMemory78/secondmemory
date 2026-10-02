"""Извлечение находок из повествовательного заключения.

В бланке анализа написано «ПСА 4,82 нг/мл». В заключении рентгенолога —
«правая почка увеличена за счет кист размерами до 40х32мм, плотность до 15HU».
Здесь нет показателей: есть ОРГАН, НАХОДКА и её СВОЙСТВА. Попытка вытащить
отсюда «показатель = число» и породила плотность несуществующего конкремента.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from ct_sample import CT                                      # noqa: E402
from app.services.findings import extract, human


def _by_organ(fs):
    return {(f["organ"], f.get("side", "")): f for f in fs}


# ── настоящее заключение ────────────────────────────────────────────────────

def test_настоящее_кт_разбирается_верно():
    fs = extract(CT)
    d = _by_organ(fs)
    assert ("kidney", "right") in d and ("kidney", "left") in d
    assert ("liver", "") in d

    right = d[("kidney", "right")]
    assert right["finding"] == "cyst"
    assert right["props"]["size"]["a"] == 40 and right["props"]["size"]["b"] == 32
    assert right["props"]["density_hu"]["max"] == 93

    left = d[("kidney", "left")]
    assert left["props"]["size"]["a"] == 37
    assert left["props"]["density_hu"]["max"] == 104


def test_стороны_не_путаются():
    """40×32 — правая, 37×31 — левая. Перепутать бок здесь дороже всего."""
    d = _by_organ(extract(CT))
    assert d[("kidney", "right")]["props"]["size"]["a"] == 40
    assert d[("kidney", "left")]["props"]["size"]["a"] == 37


def test_камней_нет_потому_что_их_нет_в_документе():
    """В заключении прямо сказано: конкрементов не содержит."""
    assert all(f["finding"] != "stone" for f in extract(CT))


def test_каждая_находка_несёт_основание():
    for f in extract(CT):
        assert f["source_span"], "нет фразы-основания"
        assert f["sources"], "не сохранены основания"


def test_одна_строка_на_орган_и_сторону():
    """Про одну почку в заключении несколько фраз — это та же находка."""
    fs = extract(CT)
    keys = [(f["organ"], f.get("side", ""), f["finding"]) for f in fs]
    assert len(keys) == len(set(keys))


# ── отдельные правила ───────────────────────────────────────────────────────

def test_отрицание_не_создаёт_находку():
    assert extract("- правая почка: конкрементов не содержит, 15 мм") == []


def test_находка_без_органа_не_сохраняется():
    assert extract("обнаружены кисты размерами 20х10мм") == []


def test_находка_без_свойств_не_сохраняется():
    assert extract("- правая почка: отмечаются кисты") == []


def test_настоящий_камень_находится():
    fs = extract("- правый мочеточник: конкремент размерами 7х5мм, плотность 920HU")
    assert len(fs) == 1
    f = fs[0]
    assert f["finding"] == "stone" and f["organ"] == "ureter"
    assert f["props"]["density_hu"]["max"] == 920


def test_орган_тянется_на_следующую_фразу():
    """«- мочеточник не расширен» идёт после «правая почка» — это про неё."""
    fs = extract("- правая почка увеличена\n- кисты размерами 12х8мм")
    assert fs and fs[0]["organ"] == "kidney" and fs[0]["side"] == "right"


def test_строка_для_врача_читается():
    fs = extract(CT)
    line = human([f for f in fs if f["organ"] == "kidney" and f["side"] == "right"][0])
    assert "Почка справа" in line and "40×32" in line and "HU" in line


# ── шкалы ───────────────────────────────────────────────────────────────────
# Шкала — не число и не находка: это классификация с закрытым списком
# значений. Прочитать «Bosniak N» нельзя, значит разбор ошибся.

from app.services.findings import extract_scales                 # noqa: E402


def test_bosniak_из_настоящего_заключения():
    sc = extract_scales(CT)
    assert len(sc) == 1
    assert sc[0]["code"] == "bosniak_class"
    assert sc[0]["value"] == "I-II"          # диапазон сохраняем как написано
    assert sc[0]["doubt"] == ""


def test_нечитаемое_значение_не_исчезает_а_вызывает_сомнение():
    """Молча пропустить ошибку чтения хуже, чем показать её врачу."""
    sc = extract_scales("Заключение: Bosniak N")
    assert len(sc) == 1 and sc[0]["value"] == "N"
    assert "не входит в допустимые" in sc[0]["doubt"]


def test_диапазон_не_превращается_в_одну_категорию():
    """«I–II» — это неопределённость врача, выбирать за него нельзя."""
    assert extract_scales("Bosniak II-III")[0]["value"] == "II-III"


def test_pirads_вне_диапазона_отмечается():
    assert extract_scales("PI-RADS 9")[0]["doubt"]


def test_глисон_сохраняет_форму():
    """3+4 и 4+3 дают одну сумму, но это разные опухоли."""
    assert extract_scales("Gleason 3+4=7")[0]["value"] == "3+4=7"


def test_шкала_несёт_основание():
    for sc in extract_scales(CT):
        assert sc["source_span"]
