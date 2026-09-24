"""Триггеры — сохранённые условия слежения (в духе Toki).

Создаются из среза по картотеке. При запуске проверяют всех пациентов и для
подходящих заводят напоминание-контроль (если ещё не заведено этим триггером).
"""
from datetime import date, timedelta
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from .. import clock
from ..reference_data import parameter_label
from ..models import Trigger, Patient, Observation, Reminder
from ..services.telemetry import log_event

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


from ..serialization import dump as _dump


class TriggerIn(BaseModel):
    name: str = ""
    parameter_code: str = "psa_total"
    op: str = ">"
    threshold: float = 4.0
    diagnosis_code: str = ""


def _matches(t: Trigger, s: Session):
    """Пациенты, у кого последнее подтверждённое значение показателя
    удовлетворяет условию триггера."""
    pts = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id(), Patient.is_training == False)).all()
    res = []
    for p in pts:
        if t.diagnosis_code and t.diagnosis_code.lower() not in (p.diagnosis_code or "").lower():
            continue
        obs = [o for o in s.exec(select(Observation).where(
            Observation.patient_id == p.id,
            Observation.parameter_code == t.parameter_code,
            Observation.status == "confirmed")).all() if o.value_num is not None]
        if not obs:
            continue
        latest = max(obs, key=lambda o: o.effective_date or date.min)
        v = latest.value_num
        ok = {">": v > t.threshold, "<": v < t.threshold,
              ">=": v >= t.threshold, "<=": v <= t.threshold}.get(t.op, False)
        if ok:
            res.append((p, v))
    return res


@router.get("")
def list_triggers(s: Session = Depends(get_session)):
    rows = s.exec(select(Trigger).where(Trigger.doctor_id == current_doctor_id())).all()
    return [{**_dump(t), "matches": len(_matches(t, s))} for t in rows]


@router.post("")
def create(body: TriggerIn, s: Session = Depends(get_session)):
    label = parameter_label(body.parameter_code)
    name = body.name or f"{label} {body.op} {body.threshold:g}" + (f" · {body.diagnosis_code}" if body.diagnosis_code else "")
    t = Trigger(doctor_id=current_doctor_id(), name=name, parameter_code=body.parameter_code,
                op=body.op, threshold=body.threshold, diagnosis_code=body.diagnosis_code)
    s.add(t); s.commit(); s.refresh(t)
    log_event(s, "trigger.created", {"parameter": body.parameter_code, "op": body.op})
    return {**_dump(t), "matches": len(_matches(t, s))}


@router.get("/{tid}/matches")
def matches(tid: int, s: Session = Depends(get_session)):
    t = s.get(Trigger, tid)
    if not t:
        raise HTTPException(404, "Триггер не найден")
    return [{"id": p.id, "short_name": p.short_name, "age": _age(p),
             "value": v, "diagnosis_code": p.diagnosis_code} for p, v in _matches(t, s)]


@router.post("/run")
def run(s: Session = Depends(get_session)):
    """Прогнать все активные триггеры: для новых совпадений завести контроль."""
    triggers = s.exec(select(Trigger).where(Trigger.doctor_id == current_doctor_id(),
                                            Trigger.active == True)).all()
    created = 0
    for t in triggers:
        tag = f"trigger{t.id}"
        for p, v in _matches(t, s):
            exists = s.exec(select(Reminder).where(
                Reminder.doctor_id == current_doctor_id(), Reminder.patient_id == p.id,
                Reminder.status == "open")).all()
            if any(tag in (r.labels or "") for r in exists):
                continue
            label = parameter_label(t.parameter_code)
            r = Reminder(doctor_id=current_doctor_id(), patient_id=p.id,
                         title=f"Контроль: {p.short_name} — {label} {v:g}",
                         kind="control", project="Контроли", priority=2,
                         parameter_code=t.parameter_code,     # структурно — для списка C01
                         labels=tag, source="trigger",
                         due_at=clock.now() + timedelta(days=1))
            s.add(r); created += 1
    s.commit()
    log_event(s, "trigger.run", {"created": created})
    return {"created": created}


@router.delete("/{tid}")
def delete(tid: int, s: Session = Depends(get_session)):
    t = s.get(Trigger, tid)
    if t:
        s.delete(t); s.commit()
    return {"ok": True}


def _age(p: Patient):
    return date.today().year - p.birth_date.year if p.birth_date else None
