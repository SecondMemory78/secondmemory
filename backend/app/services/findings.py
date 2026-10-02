"""Извлечение находок из повествовательного заключения.

Чем это отличается от разбора бланка. В анализе крови написано «ПСА 4,82
нг/мл» — название, значение, единица. В заключении рентгенолога написано так:

    «правая почка несколько увеличена за счет множественных полиморфных кист
     размерами до 40х32мм, с однородным содержимым, (в единичных кистах более
     плотное содержимое +93HU, остальные с плотностью до 15HU)»

Здесь нет показателей. Здесь есть ОРГАН (правая почка), НАХОДКА (кисты) и её
СВОЙСТВА (размер, плотность, множественность). Пытаться вытащить отсюда
«показатель = число» — ровно та ошибка, из-за которой система придумала
плотность несуществующего конкремента.

Поэтому разбираем иначе: сначала орган, потом находка, потом свойства — и
только в этом порядке. Свойство без находки не сохраняется, находка без органа
тоже. Если предложение отрицательное («конкрементов не содержит»), находка не
создаётся вовсе.

Каждая находка несёт дословную фразу-основание: врач должен видеть, из чего
она сделана.
"""
from __future__ import annotations

import re
from typing import Any

# ── Органы ──────────────────────────────────────────────────────────────────
# Сторона важна: «правая почка» и «левая почка» — разные объекты, и находки
# у них свои.
ORGANS = [
    ("kidney", "почка", ("почк",)),
    ("ureter", "мочеточник", ("мочеточник",)),
    ("bladder", "мочевой пузырь", ("мочев",)),
    ("prostate", "предстательная железа", ("предстательн", "простат")),
    ("liver", "печень", ("печен",)),
    ("adrenal", "надпочечник", ("надпочечник",)),
    ("lymph", "лимфатические узлы", ("лимфатическ",)),
]

SIDE_WORDS = [("right", ("прав",)), ("left", ("лев",)), ("both", ("обеих", "обе "))]

# ── Находки ─────────────────────────────────────────────────────────────────
FINDINGS = [
    ("cyst", "киста", ("кист",)),
    ("stone", "конкремент", ("конкремент", "камен", "камн")),
    ("tumor", "образование", ("образован", "опухол", "узел")),
    ("hydronephrosis", "расширение ЧЛС", ("гидронефроз", "расширен")),
    ("calcification", "кальцинат", ("кальцинат",)),
]

NEGATIONS = ("не выявлен", "не выявлено", "не содержит", "не обнаружен",
             "не определя", "без признаков", "отсутств", "данных за",
             "не получено", "не расширен")

# ── Свойства ────────────────────────────────────────────────────────────────
SIZE_RE = re.compile(r"(\d+[.,]?\d*)\s*[xх×]\s*(\d+[.,]?\d*)\s*(мм|см)?", re.I)
HU_RE = re.compile(r"([+\-]?\d+[.,]?\d*)\s*HU", re.I)
MULTIPLE = ("множественн", "многочисленн", "несколько", "полиморфн")
SINGLE = ("единичн", "одиночн", "солитарн")


# ── Шкалы ───────────────────────────────────────────────────────────────────
# Шкала — не число и не находка: это классификация, и у неё закрытый список
# значений. Прочитать «Bosniak N» нельзя — значит разбор ошибся, и исправлять
# «на самое похожее» недопустимо: врач должен увидеть сомнение.
# Захват НАМЕРЕННО нестрогий: берём то, что стоит после названия шкалы, и
# проверяем отдельно. Если ловить сразу только допустимые значения, «Bosniak N»
# просто исчезнет — а это ошибка чтения, о которой врач должен узнать, а не
# тишина.
SCALES = [
    ("bosniak_class", "bosniak", "Bosniak",
     re.compile(r"bosniak\s*[:\-]?\s*([^\s,.;)]{1,9})", re.I)),
    ("pirads_category", "pirads", "PI-RADS",
     re.compile(r"pi[-\s]?rads\s*[:\-]?\s*([^\s,.;)]{1,4})", re.I)),
    ("isup_grade_group", "isup", "ISUP",
     re.compile(r"isup\s*(?:grade\s*group)?\s*[:\-]?\s*([^\s,.;)]{1,4})", re.I)),
    ("gleason_score", "gleason", "Глисон", re.compile(r"gleason|глисон", re.I)),
]

GLEASON_RE = re.compile(r"(\d)\s*\+\s*(\d)(?:\s*=\s*(\d+))?")


def extract_scales(text: str) -> list[dict]:
    """Шкалы из заключения. Значение сохраняется КАК НАПИСАНО: «I–II» не
    превращаем в «1» и не выбираем из диапазона одну категорию."""
    from .fact_validator import check_categorical
    low = text or ""
    out = []
    for code, scale_key, title, rx in SCALES:
        m = rx.search(low)
        if not m:
            continue
        if code == "gleason_score":
            g = GLEASON_RE.search(low[m.start():m.start() + 120])
            raw = g.group(0).replace(" ", "") if g else ""
        else:
            raw = (m.group(1) or "").strip(" .,;:)")
        if not raw:
            continue
        why = check_categorical(scale_key, raw)
        sentence = next((x for x in _sentences(low) if raw.lower() in x.lower()), low[:200])
        out.append({"code": code, "title": title, "value": raw,
                    "doubt": why or "", "source_span": sentence.strip()[:300]})
    return out


def _sentences(text: str) -> list[str]:
    """Режем по предложениям и по пунктам списка: в заключении каждый орган
    обычно начинается с тире на новой строке."""
    parts = re.split(r"[.;\n]|(?<=\s)-\s", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _num(raw: str) -> float:
    return float(str(raw).replace(",", ".").replace("+", ""))


def extract(text: str) -> list[dict]:
    """Находки с привязкой к органу и фразой-основанием."""
    out: list[dict] = []
    current_organ: dict | None = None     # орган «тянется» на следующие фразы

    for raw in _sentences(text or ""):
        low = raw.lower()

        # 1. Орган. Если в предложении его нет — считаем, что речь всё ещё про
        #    предыдущий: «- мочеточник не расширен» идёт после «правая почка».
        organ = None
        for code, title, terms in ORGANS:
            if any(t in low for t in terms):
                side = next((s for s, words in SIDE_WORDS
                             if any(w in low for w in words)), "")
                organ = {"code": code, "title": title, "side": side}
                break
        if organ:
            current_organ = organ
        if not current_organ:
            continue                       # находка без органа не сохраняется

        # 2. Отрицание — находки в этом предложении нет вообще
        if any(n in low for n in NEGATIONS):
            continue

        # 3. Находка
        found = None
        for code, title, terms in FINDINGS:
            if any(t in low for t in terms):
                found = {"code": code, "title": title}
                break
        if not found:
            continue

        # 4. Свойства — только те, что прямо написаны
        props: dict[str, Any] = {}
        m = SIZE_RE.search(raw)
        if m:
            unit = (m.group(3) or "мм").lower()
            props["size"] = {"a": _num(m.group(1)), "b": _num(m.group(2)), "unit": unit}
        hu = [_num(x) for x in HU_RE.findall(raw)]
        if hu:
            props["density_hu"] = {"min": min(hu), "max": max(hu)}
        if any(w in low for w in MULTIPLE):
            props["count"] = "множественные"
        elif any(w in low for w in SINGLE):
            props["count"] = "единичные"

        if not props:
            continue                       # находка без единого свойства бесполезна

        out.append({
            "organ": current_organ["code"],
            "organ_title": current_organ["title"],
            "side": current_organ["side"],
            "finding": found["code"],
            "finding_title": found["title"],
            "props": props,
            # Дословная фраза: врач должен видеть, из чего сделана находка
            "source_span": raw.strip()[:300],
        })

    return _merge(out)


def _merge(items: list[dict]) -> list[dict]:
    """Одна находка на орган и сторону.

    В заключении про одну и ту же почку пишут несколько фраз: сначала размеры
    кист, потом «часть кист с тонкими перегородками». Вторая фраза — та же
    находка, а не новая, и показывать её отдельной строкой значит удваивать
    кисты на экране. Берём самую содержательную и сохраняем все основания.
    """
    best: dict = {}
    for f in items:
        key = (f["organ"], f.get("side", ""), f["finding"])
        cur = best.get(key)
        if cur is None:
            best[key] = {**f, "sources": [f["source_span"]]}
            continue
        cur["sources"].append(f["source_span"])
        # «Содержательнее» = больше свойств, кроме количества: размер и
        # плотность несут смысл, слово «единичные» само по себе — нет.
        weight = lambda x: len([k for k in x.get("props", {}) if k != "count"])
        if weight(f) > weight(cur):
            best[key] = {**f, "sources": cur["sources"]}
    return list(best.values())


SIDE_RU = {"right": "справа", "left": "слева", "both": "с обеих сторон"}


def human(f: dict) -> str:
    """Одна строка для врача: «Правая почка — кисты, множественные,
    до 40×32 мм, 15…93 HU»."""
    head = f["organ_title"].capitalize()
    if f.get("side"):
        head += " " + SIDE_RU.get(f["side"], f["side"])
    parts = [f["finding_title"]]
    p = f.get("props", {})
    if p.get("count"):
        parts.append(p["count"])
    if p.get("size"):
        s = p["size"]
        parts.append(f"до {s['a']:g}×{s['b']:g} {s['unit']}")
    if p.get("density_hu"):
        d = p["density_hu"]
        parts.append(f"{d['min']:g}…{d['max']:g} HU" if d["min"] != d["max"]
                     else f"{d['max']:g} HU")
    return f"{head} — " + ", ".join(parts)
