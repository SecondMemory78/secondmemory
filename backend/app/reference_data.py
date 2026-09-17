"""Справочные данные врача (версионируемые), загружаются один раз при старте.

Глубокий модуль: за простым интерфейсом (parameters(), find_icd(), allergy_groups())
скрыты файлы, версии и поиск. Данные — read-only, официальные источники РФ.
"""
import json
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent / "reference"


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    with open(_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def parameters() -> list[dict]:
    return _load("parameters")["items"]


def parameters_version() -> dict:
    return _load("parameters")["version"]


def parameter_label(code: str) -> str:
    return label_map().get(code, code)


@lru_cache(maxsize=None)
def label_map() -> dict:
    return {p["code"]: p["name"] for p in parameters()}


@lru_cache(maxsize=None)
def unit_map() -> dict:
    return {p["code"]: p["unit"] for p in parameters()}


@lru_cache(maxsize=None)
def synonyms_index() -> dict:
    """{code: [термины в нижнем регистре]} — для распознавания бланков (OCR)."""
    idx = {}
    for p in parameters():
        terms = [p["name"]] + list(p.get("synonyms", []))
        idx[p["code"]] = sorted({t.lower() for t in terms if t}, key=len, reverse=True)
    return idx


def common_parameters(limit: int = 40) -> list[dict]:
    """Наиболее приоритетные параметры (для выпадающих списков)."""
    order = {"Критический": 0, "Высокий": 1, "Средний": 2, "Низкий": 3}
    items = sorted(parameters(), key=lambda p: order.get(p["mvp_priority"], 9))
    return [{"code": p["code"], "name": p["name"], "unit": p["unit"]} for p in items[:limit]]


def find_icd(query: str = "", limit: int = 30) -> list[dict]:
    items = _load("icd_urology")["items"]
    q = query.strip().lower()
    if not q:
        return items[:limit]
    hits = [x for x in items if q in x["code"].lower() or q in x["title"].lower()]
    return hits[:limit]


def allergy_groups() -> list[dict]:
    return _load("allergy_groups")["items"]


# ---- препараты, бренды, нормализация ----
@lru_cache(maxsize=None)
def drugs() -> list[dict]:
    return _load("drugs")["items"]


@lru_cache(maxsize=None)
def drug_aliases() -> list[dict]:
    return _load("drug_aliases")["items"]


@lru_cache(maxsize=None)
def _alias_to_inn() -> dict:
    by_id = {d["id"]: (d["inn_ru"] or "").lower() for d in drugs()}
    idx = {}
    for a in drug_aliases():
        inn = by_id.get(a["drug_id"], "")
        if a["normalized"] and inn:
            idx[a["normalized"]] = inn
    return idx


def normalize_drug(name: str) -> str:
    """Бренд → МНН (нижний регистр). Если не бренд — вернём как есть."""
    n = (name or "").strip().lower()
    return _alias_to_inn().get(n, n)


def search_drugs(q: str, limit: int = 20) -> list[dict]:
    ql = (q or "").strip().lower()
    if not ql:
        return []
    hits = [d for d in drugs() if ql in (d["inn_ru"] + " " + d["inn_en"] + " " + d["brands"]).lower()]
    return hits[:limit]


def cross_reactions() -> list[dict]:
    return _load("cross_reactions")["items"]


def hidden_allergens() -> list[dict]:
    return _load("hidden_allergens")["items"]


def phenotypes() -> list[dict]:
    return _load("phenotypes")["items"]


def classifications() -> list[dict]:
    return _load("classifications")["items"]


# ---- полный МКБ-10 (из полного дампа листа) ----
@lru_cache(maxsize=None)
def _icd_full_raw() -> dict:
    fn = _load("manifest")["sheets"]["МКБ10_полный"]["file"]  # напр. full/mkb10_polnyy.json
    return _load(fn.replace(".json", ""))


def find_icd_full(query: str = "", limit: int = 30) -> list[dict]:
    raw = _icd_full_raw()
    cols = raw["columns"]; rows = raw["rows"]
    ci = cols.index("Код МКБ-10"); ti = cols.index("Официальное название")
    q = (query or "").strip().lower()
    out = []
    for r in rows:
        code = str(r[ci]).strip(); title = str(r[ti]).strip()
        if not code or not code[0].isalpha():
            continue
        if not q or q in code.lower() or q in title.lower():
            out.append({"code": code, "title": title.capitalize()})
            if len(out) >= limit:
                break
    return out


def icd_title(code: str) -> str:
    for x in _load("icd_urology")["items"]:
        if x["code"] == code:
            return x["title"]
    return ""
