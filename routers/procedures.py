"""Операции и процедуры.

Раньше их не было как сущности: операция терялась в заметках врача, и ни
выписка, ни вопрос «какая последняя операция» собрать её не могли.

Два правила, общие с остальной клинической частью:
- сторона не угадывается (для урологии перепутать бок — самая дорогая ошибка);
- пустое поле осложнений НЕ означает «осложнений не было»: пустое остаётся
  пустым, домысливать нельзя.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import clock
from ..db import get_session
from ..deps import current_doctor_id, get_owned_patient
from ..models import AuditEvent, Device, Procedure
from ..serialization import dump, dump_all

router = APIRouter(prefix="/api/patients", tags=["procedures"])

SIDES = {"", "left", "right", "both"}
SIDE_LABELS = {"left": "слева", "right": "справа", "both": "с обеих сторон"}


class ProcedureIn(BaseModel):
    name: str
    code: str = ""
    performed_at: Optional[date] = None
    side: str = ""
    location: str = ""
    anesthesia: str = ""
    surgeon: str = ""
    outcome: str = ""
    complications: str = ""
    note: str = ""
    device_id: Optional[int] = None
    status: str = "done"


def _view(p: Procedure) -> dict:
    d = dump(p)
    d["side_label"] = SIDE_LABELS.get(p.side, "")
    d["title"] = p.name + (f" {SIDE_LABELS[p.side]}" if p.side in SIDE_LABELS and p.side else "")
    return d


@router.get("/{pid}/procedures")
def list_procedures(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)
    rows = s.exec(select(Procedure).where(Procedure.patient_id == pid)).all()
    # Свежие сверху: «последняя операция» — самый частый вопрос.
    rows.sort(key=lambda p: (p.performed_at or date.min, p.id), reverse=True)
    return {"items": [_view(p) for p in rows]}


@router.post("/{pid}/procedures")
def add_procedure(pid: int, body: ProcedureIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)
    if not body.name.strip():
        raise HTTPException(400, "Укажите, что сделано")
    if body.side not in SIDES:
        raise HTTPException(400, "Сторона: left, right, both или пусто")
    if body.performed_at and body.performed_at > clock.today():
        raise HTTPException(400, "Дата операции в будущем — проверьте дату")
    if body.device_id:
        dev = s.get(Device, body.device_id)
        if not dev or dev.patient_id != pid:
            raise HTTPException(400, "Устройство не найдено у этого пациента")

    from ..services.visits import active_encounter_id
    p = Procedure(patient_id=pid, encounter_id=active_encounter_id(s, pid),
                  **body.model_dump())
    s.add(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="procedure",
                     entity_id=0, action="create", detail=body.name[:120]))
    s.commit(); s.refresh(p)
    return _view(p)


@router.post("/{pid}/procedures/{proc_id}/confirm")
def confirm_procedure(pid: int, proc_id: int, s: Session = Depends(get_session)):
    """Подтвердить операцию, предложенную ассистентом."""
    get_owned_patient(s, pid)
    p = s.get(Procedure, proc_id)
    if not p or p.patient_id != pid:
        raise HTTPException(404, "Операция не найдена")
    p.confirmed = True
    p.confirmed_by = current_doctor_id()
    p.confirmed_at = clock.now()
    s.add(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="procedure",
                     entity_id=p.id, action="confirm", detail=p.name[:120]))
    from ..services.ai_journal import mark_outcome, CONFIRMED
    mark_outcome(s, "procedure", p.id, CONFIRMED)
    s.commit(); s.refresh(p)
    return _view(p)


@router.post("/{pid}/procedures/{proc_id}/remove")
def remove_procedure(pid: int, proc_id: int, s: Session = Depends(get_session)):
    """Мягкое удаление: запись остаётся, история не теряется."""
    get_owned_patient(s, pid)
    p = s.get(Procedure, proc_id)
    if not p or p.patient_id != pid:
        raise HTTPException(404, "Операция не найдена")
    p.status = "cancelled"
    p.version += 1
    s.add(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="procedure",
                     entity_id=p.id, action="remove", detail=p.name[:120]))
    s.commit()
    return {"ok": True}
