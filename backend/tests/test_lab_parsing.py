"""Разбор лабораторного бланка. Строки взяты с реального фото анализа,
на котором распознавание раньше давало неверные значения."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from app.services.parsing import parse_lab_text

BLANK = """Простата специфический антиген общий (ПСА)   7,165   нг/мл   0 - 4   07.09.2026  1.1  1
Простата специфический антиген свободный (ПСА свободный)  1,50  нг/мл  07.09.2026 1.1 1
Простата специфический антиген свободный/ простата специфический антиген общий (fPSA/tPSA) 20,9 % 15 - 99
Креатинин 118 мкмоль/л 62 - 106 07.09.2026"""


def _by_code(text):
    return {v["parameter_code"]: v for v in parse_lab_text(text)["values"]}


def test_result_is_taken_not_trailing_flags():
    """В бланке после результата идут интервал, дата и служебные флаги —
    раньше бралось последнее число и ПСА превращался в 1."""
    assert _by_code(BLANK)["psa_total"]["value_num"] == 7.165


def test_free_psa_and_ratio_recognised():
    got = _by_code(BLANK)
    assert got["psa_free"]["value_num"] == 1.5
    assert got["psa_free_ratio"]["value_num"] == 20.9


def test_creatinine_not_confused_with_reference_range():
    assert _by_code(BLANK)["creatinine"]["value_num"] == 118.0


def test_synonym_does_not_match_inside_a_word():
    """«рост» находилось внутри «простата» — ПСА уезжал в рост пациента."""
    got = _by_code("Простата специфический антиген общий (ПСА) 7,165 нг/мл")
    assert "height" not in got and got["psa_total"]["value_num"] == 7.165


def test_real_height_still_works():
    assert _by_code("Рост 178 см")["height"]["value_num"] == 178.0


def test_recognized_text_is_returned_for_review():
    out = parse_lab_text(BLANK)
    assert out["text"].startswith("Простата")      # врач видит, что прочитано


# ── подготовка фото перед распознаванием ────────────────────────────────────
def test_heic_is_rejected_with_a_clear_message():
    """iPhone снимает в HEIC — Vision его не принимает, нужно объяснить врачу."""
    from app.services.ai import prepare_image, AIError
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic" + b"\x00" * 64
    try:
        prepare_image(heic)
        assert False, "HEIC должен отклоняться"
    except AIError as e:
        assert "HEIC" in str(e) and "JPEG" in str(e)


def test_big_photo_is_downscaled():
    """Фото с телефона крупнее пределов распознавания — ужимаем."""
    import io
    from PIL import Image
    from app.services.ai import prepare_image
    img = Image.new("RGB", (6000, 4000), "white")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=95)
    out = prepare_image(buf.getvalue())
    assert max(Image.open(io.BytesIO(out)).size) <= 4000


def test_small_photo_and_pdf_pass_through():
    import io
    from PIL import Image
    from app.services.ai import prepare_image
    img = Image.new("RGB", (800, 600), "white")
    buf = io.BytesIO(); img.save(buf, "JPEG")
    small = buf.getvalue()
    assert prepare_image(small) == small
    pdf = b"%PDF-1.7 minimal"
    assert prepare_image(pdf) == pdf


# ── распознавание таблиц: каждая ячейка отдельной строкой ───────────────────
# Именно так Vision отдаёт бланк с фото: название, значение, единица,
# референс и дата идут ПОДРЯД, каждое со своей строки. Раньше парсер искал
# число в той же строке, что и название, и находил ноль показателей.
TABLE = """Опухолевые маркеры
Простата специфический антиген общий (ПСА)
7,165
нг/мл
0 - 4
07.09.2026
1.1
1
Простата специфический антиген свободный (ПСА
свободный)
1,50
нг/мл
07.09.2026
Простата специфический антиген свободный/ простата
сгіецифический антиген общий ( fPSA/ tPSA)
20,9
%
15 - 99"""


def test_table_layout_is_parsed():
    got = _by_code(TABLE)
    assert got["psa_total"]["value_num"] == 7.165
    assert got["psa_free"]["value_num"] == 1.5
    assert got["psa_free_ratio"]["value_num"] == 20.9


def test_table_layout_keeps_units():
    got = _by_code(TABLE)
    assert got["psa_total"]["unit"] == "нг/мл" and got["psa_free_ratio"]["unit"] == "%"


def test_reference_interval_on_its_own_line_is_not_a_value():
    """«0 - 4» и дата идут после результата — не должны стать значением."""
    got = _by_code("Креатинин\n118\nмкмоль/л\n62 - 106\n07.09.2026")
    assert got["creatinine"]["value_num"] == 118.0


def test_parameter_without_a_value_is_skipped():
    """Значения нет — ничего не выдумываем, берём следующий показатель."""
    got = _by_code("Простата специфический антиген общий (ПСА)\nКреатинин\n118\nмкмоль/л")
    assert "psa_total" not in got and got["creatinine"]["value_num"] == 118.0


def test_ocr_spacing_inside_a_term_still_matches():
    """Распознавание вставляет пробелы: «( fPSA/ tPSA)»."""
    got = _by_code("соотношение ( fPSA/ tPSA)\n20,9\n%")
    assert got["psa_free_ratio"]["value_num"] == 20.9


# ── дата показателя (жалоба: «дата раньше даты рождения пациента») ──────────
HEADER = ("Заказ № 22188329 4 сентября 2026 г.\n"
          "Пациент: Ефимов Михаил Юрьевич\n"
          "Пол: Мужской, дата рождения: 22.01.1964, возраст: 62 года\n")


def test_birth_date_is_not_used_as_result_date():
    """В шапке бланка дата рождения идёт ПЕРВОЙ — брать её нельзя."""
    got = _by_code(HEADER + "Простата специфический антиген общий (ПСА)\n7,165\nнг/мл\n0 - 4\n07.09.2026")
    assert got["psa_total"]["effective_date"] == "2026-09-07"


def test_each_value_takes_its_own_execution_date():
    text = (HEADER +
            "Простата специфический антиген общий (ПСА)\n7,165\nнг/мл\n0 - 4\n07.09.2026\n"
            "Простата специфический антиген свободный (ПСА свободный)\n1,50\nнг/мл\n08.09.2026")
    got = _by_code(text)
    assert got["psa_total"]["effective_date"] == "2026-09-07"
    assert got["psa_free"]["effective_date"] == "2026-09-08"


def test_implausibly_old_date_is_ignored():
    """Анализ 60-летней давности не бывает — такую дату не берём."""
    got = _by_code("дата рождения: 22.01.1964\nКреатинин\n118\nмкмоль/л")
    assert got["creatinine"]["effective_date"] is None
