"""Разбор распознанного текста бланка в значения показателей (T7).

Синонимы берём из справочника врача (279 параметров), а не из захардкоженного
списка. Так OCR распознаёт все параметры словаря, а не 6 зашитых.
Значения всё равно попадают в карту как pending — врач подтверждает.
"""
import re
from typing import Dict, Any
from ..reference_data import synonyms_index, unit_map

DATE_RE = re.compile(r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})")
NUM_RE = re.compile(r"(-?\d+[.,]?\d*)")
UNITS = ["нг/мл/см³", "мкмоль/л", "ммоль/л", "нг/мл", "мл/с", "см³", "г/л", "Ед/л",
         "мм рт.ст.", "баллы", "балл", "%", "мл", "мг"]


# Дата рождения пациента печатается в шапке бланка РАНЬШЕ даты анализа.
# Брать первую дату документа нельзя: показатель уезжал в 1964 год.
_BIRTH_NEAR = re.compile(r"(?:дата\s+рождени\w*|д\.?\s?р\.?|年)[^0-9]{0,15}"
                         r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", re.I)


def _doc_date(text: str):
    """Дата документа: дату рождения и явно старые даты исключаем."""
    birth = {m.group(1) for m in _BIRTH_NEAR.finditer(text)}
    from datetime import date as _date
    this_year = _date.today().year
    for m in DATE_RE.finditer(text):
        raw = m.group(0)
        if raw in birth:
            continue
        year = int(m.group(3))
        if year < this_year - 15 or year > this_year + 1:
            continue                      # анализ 60-летней давности не бывает
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


from .fact_validator import check as validate_fact


def parse_lab_text(text: str) -> Dict[str, Any]:
    low = text.lower()
    eff = _doc_date(text)

    idx = synonyms_index()
    units = unit_map()
    values = []
    rejected = []          # что отклонено и почему — врач должен это видеть
    seen = set()
    lines = low.splitlines()

    for i, line in enumerate(lines):
        for code, terms in idx.items():
            if code in seen:
                continue
            # По ГРАНИЦАМ СЛОВ: обычное вхождение находило «рост» внутри
            # «простата», и ПСА уезжал в рост пациента.
            hit = next((t for t in terms if _word_in(t, line)), None)
            if not hit:
                continue

            # (а) значение в той же строке — обычный текстовый бланк.
            #     Берём ПЕРВОЕ число ПОСЛЕ названия: в конце строки стоят
            #     референсный интервал, дата и служебные флаги.
            m_hit = _WORD_CACHE[hit].search(line)
            tail = _cut_reference(line[m_hit.end():] if m_hit else "")
            nums = NUM_RE.findall(tail)
            unit = _unit(tail) or _unit(line)

            # (б) распознавание таблиц отдаёт каждую ячейку ОТДЕЛЬНОЙ строкой:
            #     «Простата специфический антиген общий (ПСА)» / «7,165» /
            #     «нг/мл» / «0 - 4». Значит результат ищем в следующих строках.
            if not nums:
                nums, unit = _value_from_next_lines(lines, i, idx)

            if nums:
                # у каждого показателя своя дата выполнения; нет — берём общую
                candidate = {"parameter_code": code,
                             "value_num": float(nums[0].replace(",", ".")),
                             "unit": unit or units.get(code, ""),
                             "effective_date": _date_after(lines, i) or eff,
                             "source_span": line.strip()[:200]}

                # Валидатор стоит между разбором и записью. Он не угадывает и
                # ничего не исправляет — только отклоняет. Пропустить значение
                # не страшно, врач внесёт руками; выдумать — страшно.
                why = validate_fact(candidate, context_line=line, full_text=low)
                if why:
                    rejected.append({**candidate, "why": why})
                else:
                    values.append(candidate)
                seen.add(code)
            break

    # Повествовательное заключение разбираем иначе: там не показатели, а
    # находки с органом и свойствами.
    from .findings import extract as extract_findings, extract_scales
    return {"text": text, "extracted_name": "", "extracted_dob": "",
            "values": values, "rejected": rejected,
            "findings": extract_findings(text),
            "scales": extract_scales(text)}


def _date_after(lines, i, look_ahead: int = 6):
    """Дата выполнения из той же строки таблицы — она идёт после результата."""
    from datetime import date as _date
    this_year = _date.today().year
    for j in range(i, min(i + 1 + look_ahead, len(lines))):
        m = DATE_RE.search(lines[j])
        if m and this_year - 15 <= int(m.group(3)) <= this_year + 1:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _value_from_next_lines(lines, i, idx, look_ahead: int = 4):
    """Результат из соседних строк (таблица по ячейкам).

    Идём вниз до первой строки-числа. Останавливаемся, если встретили название
    другого показателя — значит у этого значения нет и придумывать его нельзя.
    Референсный интервал («0 - 4») и дату пропускаем: они идут ПОСЛЕ результата.
    """
    unit = ""
    for j in range(i + 1, min(i + 1 + look_ahead, len(lines))):
        cell = lines[j].strip()
        if not cell:
            continue
        if _looks_like_reference(cell):          # «0 - 4», «15 - 99», дата
            continue
        if not unit:
            unit = _unit(cell)
        if _unit(cell) and not NUM_RE.search(cell.replace(_unit(cell), "")):
            continue                              # строка только с единицей
        for terms in idx.values():               # начался другой показатель
            if any(len(t) >= 4 and _word_in(t, cell) for t in terms):
                return [], unit
        nums = NUM_RE.findall(_cut_reference(cell))
        if nums:
            return nums, unit
    return [], unit


def _looks_like_reference(cell: str) -> bool:
    """«0 - 4», «15 - 99», «07.09.2026» — это не результат."""
    return bool(_REF_TAIL.fullmatch(cell.strip()) or DATE_RE.fullmatch(cell.strip()))


_WORD_CACHE = {}


def _word_in(term: str, line: str) -> bool:
    """Термин как отдельное слово (с учётом скобок и знаков вокруг)."""
    rx = _WORD_CACHE.get(term)
    if rx is None:
        rx = re.compile(r"(?<![а-яёa-z0-9])" + re.escape(term) + r"(?![а-яёa-z0-9])", re.I)
        _WORD_CACHE[term] = rx
    if rx.search(line):
        return True
    # Распознавание вставляет лишние пробелы: «( fPSA/ tPSA)». Для длинных
    # терминов сравниваем ещё и без пробелов, чтобы это не мешало.
    if len(term) >= 6:
        compact_term = re.sub(r"\s+", "", term)
        if len(compact_term) >= 6 and compact_term in re.sub(r"\s+", "", line):
            return True
    return False


# Референсный интервал («0 - 4», «15-99») и дата исполнения идут ПОСЛЕ результата —
# обрезаем хвост, чтобы они не попадали в разбор.
_REF_TAIL = re.compile(r"\d+(?:[.,]\d+)?\s*[-–—]\s*\d+(?:[.,]\d+)?|\d{2}\.\d{2}\.\d{2,4}")


def _cut_reference(tail: str) -> str:
    m = _REF_TAIL.search(tail)
    return tail[:m.start()] if m else tail


def _unit(line: str) -> str:
    for u in UNITS:
        if u.lower() in line:
            return u
    return ""
