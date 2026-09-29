"""Справка по имплантам и МР-совместимости (implants.json).

Принципы (совпадают с пометками источника и общей линией продукта):
- Система НИКОГДА не выдаёт допуск к МРТ и не говорит «безопасно». Допуск даёт
  врач по актуальной инструкции КОНКРЕТНОЙ модели и полной системы.
- Совпадение по названию/семейству — это ПОДСКАЗКА «вот что проверить», а не
  идентификация импланта пациента: у одного семейства бывают разные модели с
  разным МР-статусом.
- «Нет данных» ≠ безопасно. Ничего не выдумываем.
- Категория устройства (чек-лист) не определяет МР-статус — это только перечень
  вопросов для сбора анамнеза.
"""
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "reference" / "implants.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def devices() -> list[dict]:
    return _data()["devices"]


def checklist() -> list[dict]:
    return _data()["checklist"]


def _public(d: dict) -> dict:
    """Что отдаём наружу — без служебных полей поиска."""
    return {k: v for k, v in d.items() if k != "search_terms"}


def search_devices(q: str, limit: int = 10) -> list[dict]:
    """Поиск устройства по модели/артикулу/названию/синонимам.

    Точное совпадение по терму (например, артикул «L310») идёт раньше
    частичного, чтобы номер модели не тонул в семействах.
    """
    ql = (q or "").strip().lower()
    if len(ql) < 2:
        return []
    exact, partial = [], []
    for d in devices():
        terms = d.get("search_terms", [])
        if any(ql == t for t in terms):
            exact.append(d)
        elif any(ql in t for t in terms):
            partial.append(d)
    return [_public(d) for d in (exact + partial)[:limit]]


def mr_reference(q: str) -> dict:
    """Справка по МР-совместимости для введённого импланта.

    Возвращает найденные записи + единую памятку. Никакого вердикта
    «можно/нельзя делать МРТ» — только что проверить и у кого уточнить.
    """
    found = search_devices(q)
    if not found:
        return {"found": False, "devices": [], "message": ""}

    statuses = sorted({d["mr_status"] for d in found if d.get("mr_status")})
    message = ("Найдены справочные записи по этому устройству. Допуск к МРТ "
               "система не выдаёт: нужна точная модель, полная система "
               "(генератор + все электроды/компоненты) и актуальная инструкция "
               "производителя. Статус по справке: " + ", ".join(statuses) + ".")
    return {"found": True, "devices": found, "message": message}


# Врач говорит «кардиостимулятор», а в данных — «ЭКС». Без этого подсказка
# просто не находилась.
_ASK_SYNONYMS = {
    "кардиостимулятор": "экс", "водитель ритма": "экс", "пейсмекер": "экс",
    "дефибриллятор": "икд", "кардиовертер": "икд",
    "нейростимулятор": "стимулятор", "стимулятор спинного мозга": "стимулятор",
    "эндопротез": "протез", "искусственный сустав": "протез",
    "кохлеар": "кохлеарный", "улитка": "кохлеарный",
    "жж-стент": "стент", "мочеточниковый стент": "стент",
    "порт": "порт-система", "помпа": "помпа",
    "клипса": "клипс", "спираль": "койл",
}


def _expand(ql: str) -> str:
    """Добавляем к запросу термин из данных, если врач сказал по-своему."""
    extra = [v for k, v in _ASK_SYNONYMS.items() if k and k in ql and v]
    return (ql + " " + " ".join(extra)).strip() if extra else ql


def checklist_search(q: str, limit: int = 6) -> list[dict]:
    """Что спросить по этому устройству. Подсказка врачу в момент работы.

    ВАЖНО: это вопросы для сбора анамнеза, а НЕ МР-статус — сам источник
    подчёркивает, что категория устройства статус не определяет.
    """
    ql = _expand((q or "").strip().lower())
    if len(ql) < 3:
        return []
    words = [w for w in ql.split() if len(w) >= 3]
    hits = []
    for row in checklist():
        hay = f"{row.get('ask', '')} {row.get('area', '')} {row.get('needed', '')}".lower()
        score = sum(1 for w in words if w in hay)
        if ql in hay:
            score += 3
        if score:
            hits.append((score, row))
    hits.sort(key=lambda x: -x[0])
    return [r for _, r in hits[:limit]]


def checklist_for(area: str = "") -> list[dict]:
    """Перечень вопросов для сбора анамнеза (по области или весь).
    Категория НЕ определяет МР-статус — это только что спросить."""
    al = (area or "").strip().lower()
    rows = checklist()
    if al:
        rows = [c for c in rows if al in (c.get("area", "") or "").lower()]
    return rows
