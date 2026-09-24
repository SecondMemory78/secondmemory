"""Разрешение личности пациента (правила PAT из ТЗ).

Детерминированная логика (НЕ ИИ): по присланным данным находим, к какой карточке
относится материал. Общий модуль для ручного ввода, OCR и голоса.

Быстрая выборка кандидатов — по слепому индексу (name_index = HMAC фамилии+имени),
без загрузки и расшифровки всех карточек. Тонкая логика (отчество, дата рождения,
пол) применяется уже к небольшому набору кандидатов.

action: use | choose | similar | conflict | new (поведение см. в роутере).
"""
from sqlmodel import Session, select
from ..models import Patient, PatientExternalId
from ..crypto import blind_index


def name_index_for(last: str, first: str) -> str:
    """Слепой индекс по фамилии+имени — ключ для быстрой точной выборки кандидатов."""
    return blind_index(f"{(last or '').strip()}|{(first or '').strip()}")


def _norm(v: str) -> str:
    return (v or "").strip().lower().replace("ё", "е")


def _display(p: Patient) -> dict:
    fio = " ".join(x for x in [p.last_name, p.first_name, p.middle_name] if x)
    return {"id": p.id, "name": fio,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "sex": p.sex, "identity_status": p.identity_status}


def resolve_identity(s: Session, doctor_id: int, q: dict, mode: str = "auto") -> dict:
    # 1) Точный внешний ID с названием системы
    if q.get("external_system") and q.get("external_value"):
        ext = s.exec(select(PatientExternalId).where(
            PatientExternalId.system == q["external_system"],
            PatientExternalId.value == q["external_value"])).first()
        if ext:
            p = s.get(Patient, ext.patient_id)
            if p and p.doctor_id == doctor_id:
                if q.get("birth_date") and p.birth_date and q["birth_date"] != p.birth_date:
                    return {"action": "conflict", "reason": "external_id_dob_conflict",
                            "candidates": [_display(p)],
                            "message": "Внешний ID указывает на карточку с другой датой рождения."}
                return {"action": "use", "patient_id": p.id, "candidates": [_display(p)]}

    last, first, middle = q.get("last_name"), q.get("first_name"), q.get("middle_name")
    if not last or not first:
        return {"action": "new", "reason": "insufficient_data", "candidates": []}

    qmid = _norm(middle)
    idx = name_index_for(last, first)
    same_name_all = s.exec(select(Patient).where(
        Patient.doctor_id == doctor_id, Patient.name_index == idx,
        Patient.is_training == False)).all()

    def middle_ok(p):
        pm = _norm(p.middle_name)
        return not (qmid and pm and qmid != pm)   # отчество: совпадает или отсутствует с одной стороны
    name_matches = [p for p in same_name_all
                    if not (p.identity_status or "").startswith("merged_into") and middle_ok(p)]

    if not name_matches:
        return {"action": "new", "candidates": []}

    if q.get("birth_date"):
        dob_matches = [p for p in name_matches if p.birth_date == q["birth_date"]]
        if len(dob_matches) == 1:
            p = dob_matches[0]
            if q.get("sex") and p.sex and q["sex"] != p.sex:
                return {"action": "conflict", "reason": "sex_conflict",
                        "candidates": [_display(p)],
                        "message": "Пол не совпадает с подтверждённой карточкой."}
            return {"action": "use", "patient_id": p.id, "candidates": [_display(p)]}
        if len(dob_matches) >= 2:
            return {"action": "choose", "reason": "duplicate_demographics",
                    "candidates": [_display(p) for p in dob_matches]}
        return {"action": "similar", "reason": "name_match_dob_differs",
                "candidates": [_display(p) for p in name_matches]}

    if len(name_matches) == 1:
        return {"action": "use", "patient_id": name_matches[0].id,
                "candidates": [_display(name_matches[0])], "reason": "name_only_single"}
    return {"action": "choose", "reason": "name_only_multiple",
            "candidates": [_display(p) for p in name_matches]}
