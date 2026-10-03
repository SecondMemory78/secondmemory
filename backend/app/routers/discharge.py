"""Выписка по эпизоду: черновик → правка врачом → подпись.

Почему не «сформировать и скачать». Документ подписывает врач своим именем,
поэтому собранный текст — это предложение, а не результат. Врач правит
формулировки, видит, что НЕ вошло и почему, и только потом подписывает.

Подписанная версия неизменяема. Нужна правка — создаётся новая версия, старая
остаётся: в медицинском документе подмена задним числом недопустима.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import clock
from ..db import get_session
from ..deps import current_doctor_id, get_owned_patient
from ..models import AuditEvent, Discharge, Encounter
from ..services.discharge import build_draft, checks

router = APIRouter(prefix="/api", tags=["discharge"])


def _owned(s: Session, did: int) -> Discharge:
    d = s.get(Discharge, did)
    if not d or d.doctor_id != current_doctor_id():
        raise HTTPException(404, "Выписка не найдена")
    return d


def _view(s: Session, d: Discharge) -> dict:
    return {
        "id": d.id, "encounter_id": d.encounter_id, "patient_id": d.patient_id,
        "status": d.status, "version": d.version,
        "sections": json.loads(d.sections or "{}"),
        "excluded": json.loads(d.excluded or "[]"),
        "checks": checks(s, d) if d.status == "draft" else [],
        "finalized_at": d.finalized_at.isoformat() if d.finalized_at else None,
    }


@router.post("/encounters/{eid}/discharge")
def create_draft(eid: int, s: Session = Depends(get_session)):
    """Собрать черновик. Повторный вызов на том же эпизоде возвращает
    существующий черновик, а не плодит новые."""
    enc = s.get(Encounter, eid)
    if not enc:
        raise HTTPException(404, "Эпизод не найден")
    get_owned_patient(s, enc.patient_id)

    exists = s.exec(select(Discharge).where(
        Discharge.encounter_id == eid, Discharge.status == "draft")).first()
    if exists:
        return _view(s, exists)

    built = build_draft(s, eid)
    d = Discharge(doctor_id=current_doctor_id(), patient_id=enc.patient_id,
                  encounter_id=eid,
                  sections=json.dumps(built["sections"], ensure_ascii=False),
                  excluded=json.dumps(built["excluded"], ensure_ascii=False),
                  # Снимок исходных данных: чем объяснять цифры через год.
                  source_snapshot=json.dumps(built["sections"], ensure_ascii=False))
    s.add(d)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="discharge",
                     entity_id=0, action="draft", detail=f"эпизод {eid}"))
    s.commit(); s.refresh(d)
    return _view(s, d)


@router.get("/discharge/{did}")
def get_discharge(did: int, s: Session = Depends(get_session)):
    return _view(s, _owned(s, did))


class SectionsIn(BaseModel):
    sections: dict


@router.patch("/discharge/{did}")
def edit(did: int, body: SectionsIn, s: Session = Depends(get_session)):
    """Правка врача. Подписанную версию менять нельзя."""
    d = _owned(s, did)
    if d.status == "final":
        raise HTTPException(400, "Выписка подписана. Создайте новую версию, "
                                 "подписанную менять нельзя")
    d.sections = json.dumps(body.sections, ensure_ascii=False)
    d.updated_at = clock.now()
    s.add(d); s.commit(); s.refresh(d)
    return _view(s, d)


@router.post("/discharge/{did}/finalize")
def finalize(did: int, s: Session = Depends(get_session)):
    """Подписать. Проверки не блокируют — врач видел их и принял решение."""
    d = _owned(s, did)
    if d.status == "final":
        raise HTTPException(400, "Выписка уже подписана")
    d.status = "final"
    d.finalized_by = current_doctor_id()
    d.finalized_at = clock.now()
    s.add(d)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="discharge",
                     entity_id=d.id, action="finalize",
                     detail=f"версия {d.version}"))
    s.commit(); s.refresh(d)
    return _view(s, d)


@router.post("/discharge/{did}/revise")
def revise(did: int, s: Session = Depends(get_session)):
    """Новая версия поверх подписанной. Старая остаётся нетронутой —
    подменять подписанный документ задним числом нельзя."""
    old = _owned(s, did)
    if old.status != "final":
        raise HTTPException(400, "Создавать версию можно только от подписанной")
    new = Discharge(doctor_id=old.doctor_id, patient_id=old.patient_id,
                    encounter_id=old.encounter_id, status="draft",
                    version=old.version + 1,
                    sections=old.sections, excluded=old.excluded,
                    source_snapshot=old.source_snapshot)
    s.add(new)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="discharge",
                     entity_id=old.id, action="revise",
                     detail=f"версия {new.version}"))
    s.commit(); s.refresh(new)
    return _view(s, new)


@router.get("/patients/{pid}/discharges")
def list_for_patient(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)
    rows = s.exec(select(Discharge).where(Discharge.patient_id == pid)).all()
    rows.sort(key=lambda d: (d.encounter_id, d.version), reverse=True)
    return {"items": [{"id": d.id, "encounter_id": d.encounter_id,
                       "status": d.status, "version": d.version,
                       "finalized_at": d.finalized_at.isoformat() if d.finalized_at else None}
                      for d in rows]}
