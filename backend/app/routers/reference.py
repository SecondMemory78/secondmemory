from fastapi import APIRouter
from ..reference_data import (parameters, parameters_version, find_icd, allergy_groups,
                              common_parameters, label_map)

router = APIRouter(prefix="/api/reference", tags=["reference"])


@router.get("/parameters/common")
def get_common(limit: int = 40):
    return {"items": common_parameters(limit)}


@router.get("/parameters/labels")
def get_labels():
    return label_map()


@router.get("/parameters/meta")
def get_meta():
    """Компактные метаданные по каждому параметру для графиков: имя, единица, порог.
    Порог — текстовая подсказка; если начинается с числа, фронт может нарисовать линию порога."""
    return {p["code"]: {"name": p.get("name", p["code"]), "unit": p.get("unit", ""),
                        "threshold": p.get("threshold", "")}
            for p in parameters()}


@router.get("/parameters")
def get_parameters(priority: str = ""):
    items = parameters()
    if priority:
        items = [p for p in items if p["mvp_priority"].lower() == priority.lower()]
    return {"version": parameters_version(), "count": len(items), "items": items}


@router.get("/icd")
def get_icd(q: str = "", limit: int = 30, scope: str = "urology"):
    from ..reference_data import find_icd_full
    return {"items": find_icd_full(q, limit) if scope == "full" else find_icd(q, limit)}


@router.get("/drugs")
def get_drugs(q: str = "", limit: int = 20):
    from ..reference_data import search_drugs
    return {"items": search_drugs(q, limit)}


@router.get("/classifications")
def get_classifications(specialty: str = ""):
    from ..reference_data import classifications
    items = classifications()
    if specialty:
        items = [x for x in items if specialty.lower() in (x.get("specialty", "").lower())]
    return {"items": items}


@router.get("/cross-reactions")
def get_cross():
    from ..reference_data import cross_reactions
    return {"items": cross_reactions()}


@router.get("/hidden-allergens")
def get_hidden():
    from ..reference_data import hidden_allergens
    return {"items": hidden_allergens()}


@router.get("/allergy-groups")
def get_allergy_groups():
    return {"items": allergy_groups()}
