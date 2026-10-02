"""Валидатор извлечённых значений — критерий приёмки из ТЗ.

На настоящем КТ почек система создавала четыре показателя, и все четыре были
неверны: доза облучения превратилась в дозу препарата, размер кисты — в
локализацию несуществующего камня, плотность содержимого кист — в плотность
конкремента. При том что в документе прямо написано: конкрементов нет.

Правило простое: пропустить значение не страшно, врач внесёт руками.
Выдумать — страшно: врач подтвердит не глядя, и в карте появится камень,
которого нет.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from ct_sample import CT                                     # noqa: E402
from app.services.fact_validator import check, check_categorical, negated_codes
from app.services.parsing import parse_lab_text


# ── критерий приёмки из ТЗ ──────────────────────────────────────────────────

def test_настоящее_кт_не_создаёт_четыре_выдумки():
    """Главный тест. Эти четыре значения появляться не должны никогда."""
    out = parse_lab_text(CT)
    codes = {v["parameter_code"] for v in out["values"]}
    for bad in ("medication_dose", "dre_findings", "stone_density", "stone_location"):
        assert bad not in codes, f"выдуманный показатель вернулся: {bad}"


def test_отклонённое_не_исчезает_молча():
    """Врач должен видеть, что именно отброшено и почему."""
    out = parse_lab_text(CT)
    assert out["rejected"], "ничего не отклонено — значит проверка не работает"
    for r in out["rejected"]:
        assert r["why"], "нет причины отклонения"


# ── тип значения ────────────────────────────────────────────────────────────

def test_локализация_не_может_быть_числом():
    why = check({"parameter_code": "stone_location", "value_num": 37, "unit": ""})
    assert why and "справочник" in why


def test_пальцевое_исследование_не_число():
    why = check({"parameter_code": "dre_findings", "value_num": 10, "unit": ""})
    assert why


def test_обычный_анализ_проходит():
    assert check({"parameter_code": "psa_total", "value_num": 4.82,
                  "unit": "нг/мл", "source_span": "ПСА общий 4,82 нг/мл"}) is None


# ── технические параметры исследования ──────────────────────────────────────

def test_доза_облучения_не_показатель_пациента():
    why = check({"parameter_code": "x", "value_num": 18, "unit": "мЗв"})
    assert why and "технический" in why


def test_строка_про_аппарат_отклоняется():
    why = check({"parameter_code": "x", "value_num": 18, "unit": ""},
                context_line="эффективная доза: 18 мЗв")
    assert why


# ── отрицания ───────────────────────────────────────────────────────────────

def test_отрицание_блокирует_камни():
    blocked = negated_codes(CT.lower())
    assert "stone_density" in blocked and "stone_size" in blocked


def test_плотность_кисты_не_становится_плотностью_камня():
    why = check({"parameter_code": "stone_density", "value_num": 15, "unit": "HU"},
                full_text=CT.lower())
    assert why and "нет" in why


def test_без_отрицания_камень_допустим():
    text = "конкремент нижней трети правого мочеточника 7х5 мм, плотность 920 HU"
    assert check({"parameter_code": "stone_density", "value_num": 920, "unit": "HU",
                  "source_span": text}, full_text=text) is None


# ── единицы ─────────────────────────────────────────────────────────────────

def test_чужая_единица_отклоняется():
    why = check({"parameter_code": "stone_density", "value_num": 7, "unit": "мм"})
    assert why and "единица" in why


def test_без_единицы_там_где_она_обязательна():
    why = check({"parameter_code": "psa_total", "value_num": 4.8, "unit": ""})
    assert why and "единица" in why


# ── шкалы ───────────────────────────────────────────────────────────────────

def test_bosniak_буква_N_не_проходит():
    """В тестовом документе OCR прочитал «Bosniak I–II» как «N»."""
    assert check_categorical("bosniak", "N")


def test_bosniak_диапазон_допустим():
    assert check_categorical("bosniak", "I–II") is None
    assert check_categorical("bosniak", "IIF") is None


def test_pirads_только_от_одного_до_пяти():
    assert check_categorical("pirads", "4") is None
    assert check_categorical("pirads", "37")


def test_gleason_сохраняет_форму():
    assert check_categorical("gleason", "3+4=7") is None
    assert check_categorical("gleason", "7")


# ── голое число без основания ───────────────────────────────────────────────

def test_число_без_фразы_основания_не_сохраняется():
    """По ТЗ ссылка на фрагмент обязательна: нет её — врачу нечего проверять."""
    why = check({"parameter_code": "hemoglobin", "value_num": 140, "unit": "г/л"})
    assert why and "основания" in why


def test_с_фразой_основания_проходит():
    assert check({"parameter_code": "hemoglobin", "value_num": 140, "unit": "г/л",
                  "source_span": "гемоглобин 140 г/л"}) is None


def test_разбор_всегда_кладёт_основание():
    """Значит настоящие бланки не пострадают от запрета выше."""
    out = parse_lab_text("ПСА общий 4,82 нг/мл\nКреатинин 98 мкмоль/л")
    assert out["values"], "обычный бланк перестал разбираться"
    for v in out["values"]:
        assert v.get("source_span"), "разбор не сохранил фразу-основание"
