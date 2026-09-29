"""Проверка назначения на конфликт с аллергиями пациента (T8).

По справочнику врача (allergy_groups.json, 124 группы). Инварианты (ADR-0003):
- система НЕ блокирует и НЕ подбирает замену — только предупреждает;
- перекрёстная реактивность показывается как правило из справочника (по структуре),
  а не выводится автоматически по классу;
- решение и причина — за врачом (пишется в аудит роутером назначений).

check_conflict возвращает структуру {level, message, group, cross_rule, phenotype}
или None. level: "high" (красный флаг из справочника) | "warn".
"""
import re
from functools import lru_cache
from typing import List, Optional
from ..models import SafetyItem
from ..reference_data import allergy_groups, normalize_drug, cross_reactions


@lru_cache(maxsize=None)
def _groups():
    out = []
    for g in allergy_groups():
        examples = [e.strip().lower() for e in re.split(r"[;,]", g.get("examples", "")) if e.strip()]
        out.append({
            "id": g["id"], "name": g["group"], "name_l": g["group"].lower(),
            "examples": examples, "cross": g.get("cross_rule", ""),
            "phenotypes": g.get("phenotypes", ""), "red": bool(g.get("show_red")),
        })
    return out


def _patient_groups(allergen: str):
    """Группы, к которым относится аллерген пациента (по названию группы или примерам)."""
    hits = []
    for g in _groups():
        if g["name_l"] and g["name_l"] in allergen:
            hits.append(g); continue
        if any(ex in allergen for ex in g["examples"] if len(ex) >= 4):
            hits.append(g)
    return hits


def check_conflict(drug_name: str, allergies: List[SafetyItem]) -> Optional[dict]:
    raw = (drug_name or "").strip().lower()
    if not raw:
        return None
    d = normalize_drug(raw)          # бренд → МНН для сопоставления
    probe = f"{raw} {d}"
    for a in allergies:
        if a.state != "present" or not a.detail:
            continue
        allergen = a.detail.strip().lower()

        # 1) прямое совпадение названия/МНН с аллергеном
        if (len(d) >= 4 and d in allergen) or (len(raw) >= 4 and raw in allergen):
            return {"level": "high", "message": f"Прямая аллергия: {a.detail}",
                    "group": "", "cross_rule": "", "phenotype": ""}

        # 2) групповое совпадение: пациент аллергичен к группе, препарат — из неё
        for g in _patient_groups(allergen):
            in_group = g["name_l"] in probe or any(ex in probe for ex in g["examples"] if len(ex) >= 4)
            if in_group:
                return {"level": "high" if g["red"] else "warn",
                        "message": f"Аллергия группы «{g['name']}»: {a.detail}",
                        "group": g["name"], "cross_rule": g["cross"], "phenotype": g["phenotypes"]}

        # 3) перекрёстная реактивность по справочнику (структурная, не по классу)
        for x in cross_reactions():
            src, rel = x["source"], x["related"]
            if src and rel and len(src) >= 4 and len(rel) >= 4 and src in allergen and rel in probe:
                return {"level": "warn", "message": f"Возможная перекрёстная реакция с «{a.detail}»",
                        "group": "", "cross_rule": f"{x['determinant']} · {x['action']}".strip(" ·"),
                        "phenotype": x["phenotype"]}
    return None
