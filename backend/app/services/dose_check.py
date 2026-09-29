"""Справка по дозам из внешней базы врача (dose_limits.json).

Принципы (совпадают с пометками самого источника и ADR по безопасности):
- Система ТОЛЬКО подсказывает «проверьте дозу», НИКОГДА не блокирует и не
  утверждает безопасность.
- «Выше типичного предела» считаем лишь для простых суточных доз в массе
  (мг/мкг) и лишь когда дозу врача удалось разобрать однозначно; иначе —
  показываем справочные пределы без вердикта (чтобы не давать ложных тревог).
- Нет данных по препарату → ничего не выдумываем (не «безопасно»).
- У каждой записи показываем источник и статус «не верифицировано».
"""
import json
from functools import lru_cache
from pathlib import Path
from ..reference_data import normalize_drug

_PATH = Path(__file__).resolve().parent.parent / "reference" / "dose_limits.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def _records():
    return _data()["records"]


def _match_key(drug_name: str) -> str:
    """Нормализуем препарат врача в тот же ключ, что и mnn_key в базе."""
    n = normalize_drug(drug_name or "")          # бренд → МНН, нижний регистр
    n = n.strip().lower()
    for sep in [" при ", ":", ";", "(", "/", " — ", "—", ","]:
        i = n.find(sep)
        if i > 0:
            n = n[:i]
    return n.strip()


def dose_reference(drug_name: str, dose_text: str = "") -> dict:
    """Справка по дозе для назначения. Ничего не блокирует и НЕ выносит
    автоматический вердикт «доза превышена»: колонка «предел: число» в базе
    — это иногда целевая/обычная доза, а не токсикологический максимум
    (прямое предупреждение источника), поэтому авто-сравнение давало бы
    ложные тревоги на легитимных дозах. Показываем справочные пределы с
    источником и нейтральное «проверьте дозу» — сравнение делает врач.

    Возвращает:
      has_reference: есть ли записи по этому МНН
      records: справочные пределы (число, единица, период, показание, источник)
      message: короткий текст-подсказка (или "")
    """
    key = _match_key(drug_name)
    if not key:
        return {"has_reference": False, "records": [], "message": ""}

    recs = [r for r in _records() if r["mnn_key"] == key]
    if not recs:
        return {"has_reference": False, "records": [], "message": ""}

    ref = [{"limit_num": r["limit_num"], "unit": r["unit"], "period": r["period"],
            "indication": r["indication"], "product": r["product"],
            "source": r["source"], "id": r["id"]} for r in recs]

    message = ("По этому препарату есть справочные пределы дозы — сверьте назначение. "
               "Справка из базы врача, статус «не верифицировано», не клиническое правило.")
    return {"has_reference": True, "records": ref, "message": message}
