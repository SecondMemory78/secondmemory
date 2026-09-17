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


def parse_lab_text(text: str) -> Dict[str, Any]:
    low = text.lower()
    eff = None
    m = DATE_RE.search(text)
    if m:
        eff = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    idx = synonyms_index()
    units = unit_map()
    values = []
    seen = set()
    for line in low.splitlines():
        for code, terms in idx.items():
            if code in seen:
                continue
            if any(t in line for t in terms):
                nums = NUM_RE.findall(line)
                if nums:
                    values.append({"parameter_code": code,
                                   "value_num": float(nums[-1].replace(",", ".")),
                                   "unit": _unit(line) or units.get(code, ""),
                                   "effective_date": eff})
                    seen.add(code)
                break
    return {"text": text, "extracted_name": "", "extracted_dob": "", "values": values}


def _unit(line: str) -> str:
    for u in UNITS:
        if u.lower() in line:
            return u
    return ""
