"""OCR + извлечение значений. Делегирует в слой ИИ (services/ai.py),
провайдер выбирается переменной AI_PROVIDER. Заглушка — по умолчанию."""
from typing import Dict, Any
from . import ai


def extract_values(image_bytes: bytes = b"") -> Dict[str, Any]:
    res = ai.ocr_extract(image_bytes)
    return {
        "ok": True,
        "text": res.get("text", ""),
        "extracted_name": res.get("extracted_name", ""),
        "extracted_dob": res.get("extracted_dob", ""),
        "values": res.get("values", []),
    }


def split_photo(image_bytes: bytes = b"", sim=None):
    """Разбивка фото на фрагменты по пациентам. Реальный анализ областей — после
    подключения Vision (тогда заменяется тело функции). Сейчас: если переданы
    симулированные фрагменты (sim) — используем их (для отладки/тестов и демо);
    иначе — один фрагмент на всё изображение.

    Формат фрагмента: {region:{x,y,w,h}, name:{last,first,middle}, birth_date, values:[...]}.
    """
    if sim:
        out = []
        n = len(sim)
        for i, f in enumerate(sim):
            out.append({
                "region": f.get("region", {"x": 0, "y": round(i / n, 3), "w": 1, "h": round(1 / n, 3)}),
                "name": {"last": f.get("last_name", ""), "first": f.get("first_name", ""),
                         "middle": f.get("middle_name", "")},
                "birth_date": f.get("birth_date", ""),
                "values": f.get("values", []),
            })
        return out
    # заглушка без sim: одна область, данные пусты (реальное распознавание позже)
    return [{"region": {"x": 0, "y": 0, "w": 1, "h": 1}, "name": {"last": "", "first": "", "middle": ""},
             "birth_date": "", "values": []}]
