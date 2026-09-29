from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from ..db import get_session
from ..deps import current_doctor_id
from ..services import cohorts

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.get("")
def all_lists(s: Session = Depends(get_session)):
    """Готовые списки пациентов со счётчиками (ТЗ §11)."""
    return {"presets": cohorts.list_presets(s, current_doctor_id())}


@router.get("/{code}")
def one_list(code: str, s: Session = Depends(get_session)):
    """Содержимое одного списка: пациенты с причиной попадания и сроком."""
    data = cohorts.preset_items(s, current_doctor_id(), code.upper())
    if data is None:
        raise HTTPException(404, "Такого списка нет")
    return data
