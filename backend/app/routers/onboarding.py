from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from ..db import get_session
from ..deps import current_doctor_id
from ..services import onboarding as ob

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class TipIn(BaseModel):
    key: str


@router.get("/progress")
def get_progress(s: Session = Depends(get_session)):
    """Что врач уже прошёл/видел: онбординг и список увиденных подсказок."""
    return ob.progress(s, current_doctor_id())


@router.post("/tips/seen")
def mark_tip_seen(body: TipIn, s: Session = Depends(get_session)):
    """Отметить точечную подсказку увиденной (идемпотентно). Только ключи из белого списка."""
    if body.key not in ob.TIP_KEYS:
        raise HTTPException(400, "Неизвестная подсказка")
    ob.mark_seen(s, current_doctor_id(), body.key)
    return {"ok": True}


@router.post("/sandbox/start")
def sandbox_start(s: Session = Depends(get_session)):
    """Начать обучение: создать учебного пациента (is_training). Идемпотентно."""
    p = ob.start_sandbox(s, current_doctor_id())
    return {"ok": True, "patient_id": p.id, "short_name": p.short_name}


class FinishIn(BaseModel):
    completed: bool = True     # True — прошёл до конца, False — пропустил; в обоих случаях больше не показываем


@router.post("/sandbox/finish")
def sandbox_finish(body: FinishIn = FinishIn(), s: Session = Depends(get_session)):
    """Завершить/пропустить обучение: удалить учебного пациента, пометить онбординг пройденным."""
    ob.finish_sandbox(s, current_doctor_id(), mark_done=True)
    return {"ok": True}
