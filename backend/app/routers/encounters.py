from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id, get_owned_patient, get_owned_encounter
from ..serialization import dump, dump_all
from ..services.consent import consent_ok
from ..services.visits import day_of_stay, open_encounters
from ..models import (Encounter, Patient, Observation, Note, Prescription,
                      SourceDocument, VisitProtocol, SickLeave)

router = APIRouter(prefix="/api", tags=["encounters"])


def _parse_dt(v):
    if not v:
        return None
    return datetime.fromisoformat(v[:19] if len(v) > 10 else v + "T00:00:00")


class EncounterIn(BaseModel):
    reason: str = ""


class EpisodeIn(BaseModel):
    type: str = "visit"                       # visit | hospitalization
    reason: str = ""
    appointment_id: Optional[int] = None
    planned_admission_at: Optional[str] = None
    actual_admission_at: Optional[str] = None
    planned_discharge_at: Optional[str] = None
    ward: str = ""
    diagnosis_code: str = ""
    diagnosis_text: str = ""


class EpisodePatch(BaseModel):
    expected_version: int
    reason: Optional[str] = None
    ward: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_text: Optional[str] = None
    planned_admission_at: Optional[str] = None
    actual_admission_at: Optional[str] = None
    planned_discharge_at: Optional[str] = None
    actual_discharge_at: Optional[str] = None


def _summary(s: Session, eid: int):
    def n(model):
        return len(s.exec(select(model).where(model.encounter_id == eid)).all())
    return {"observations": n(Observation), "notes": n(Note),
            "prescriptions": n(Prescription), "documents": n(SourceDocument)}


def _view(e: Encounter, s: Session = None):
    d = dump(e)
    d["day_of_stay"] = day_of_stay(e)
    if s is not None:
        d["summary"] = _summary(s, e.id)
    return d


# ── Совместимость: быстрый амбулаторный приём (одна открытая сессия типа visit) ──
@router.post("/patients/{pid}/encounters")
def start(pid: int, body: EncounterIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                   # чужой/несуществующий пациент → 404
    if not consent_ok(s, pid):
        raise HTTPException(403, "Нет согласия на обработку ПДн — приём вести нельзя. Оформите согласие.")
    e = s.exec(select(Encounter).where(Encounter.patient_id == pid,
                                       Encounter.type == "visit",
                                       Encounter.status == "open")).first()
    if not e:
        e = Encounter(doctor_id=current_doctor_id(), patient_id=pid, reason=body.reason)
        s.add(e); s.commit(); s.refresh(e)
    return _view(e)


# ── Богатое создание эпизода (в т.ч. госпитализации) — всегда новый ──
@router.post("/patients/{pid}/episodes")
def create_episode(pid: int, body: EpisodeIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                   # чужой/несуществующий пациент → 404
    if not consent_ok(s, pid):
        raise HTTPException(403, "Нет согласия на обработку ПДн — вести эпизод нельзя. Оформите согласие.")
    e = Encounter(doctor_id=current_doctor_id(), patient_id=pid,
                  type=body.type if body.type in ("visit", "hospitalization") else "visit",
                  reason=body.reason, appointment_id=body.appointment_id, ward=body.ward,
                  diagnosis_code=body.diagnosis_code, diagnosis_text=body.diagnosis_text,
                  planned_admission_at=_parse_dt(body.planned_admission_at),
                  actual_admission_at=_parse_dt(body.actual_admission_at),
                  planned_discharge_at=_parse_dt(body.planned_discharge_at))
    s.add(e); s.commit(); s.refresh(e)
    return _view(e, s)


@router.get("/patients/{pid}/episodes")
def episodes(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                   # чужой/несуществующий пациент → 404
    rows = s.exec(select(Encounter).where(Encounter.patient_id == pid)).all()
    rows.sort(key=lambda e: e.started_at, reverse=True)
    open_count = sum(1 for e in rows if e.status == "open")
    return {"open_count": open_count, "items": [_view(e, s) for e in rows]}


# алиас старого имени истории
@router.get("/patients/{pid}/encounters")
def history(pid: int, s: Session = Depends(get_session)):
    return episodes(pid, s)["items"]


@router.get("/patients/{pid}/encounters/active")
def active(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                   # чужой/несуществующий пациент → 404
    rows = open_encounters(s, pid)
    return _view(rows[0]) if len(rows) == 1 else None


@router.get("/encounters/{eid}")
def detail(eid: int, s: Session = Depends(get_session)):
    e = get_owned_encounter(s, eid)             # чужой/несуществующий эпизод → 404

    def items(model):
        return dump_all(s.exec(select(model).where(model.encounter_id == eid)).all())
    d = _view(e)
    d.update({"observations": items(Observation), "notes": items(Note),
              "prescriptions": items(Prescription), "documents": items(SourceDocument),
              "protocol": dump(s.exec(select(VisitProtocol).where(VisitProtocol.encounter_id == eid)).first())})
    return d


@router.patch("/episodes/{eid}")
def update_episode(eid: int, body: EpisodePatch, s: Session = Depends(get_session)):
    e = s.get(Encounter, eid)
    if not e or e.doctor_id != current_doctor_id():
        raise HTTPException(404, "Эпизод не найден")
    if e.version != body.expected_version:
        raise HTTPException(409, "Эпизод был изменён с другого устройства. Обновите и повторите.")
    data = body.model_dump(exclude_unset=True)
    for f in ("reason", "ward", "diagnosis_code", "diagnosis_text"):
        if data.get(f) is not None:
            setattr(e, f, data[f])
    for f in ("planned_admission_at", "actual_admission_at", "planned_discharge_at", "actual_discharge_at"):
        if f in data:
            setattr(e, f, _parse_dt(data[f]))
    e.version += 1
    s.add(e); s.commit(); s.refresh(e)
    return _view(e, s)


@router.post("/encounters/{eid}/close")
def close(eid: int, s: Session = Depends(get_session)):
    e = get_owned_encounter(s, eid)             # чужой/несуществующий эпизод → 404
    if e.status == "open":
        e.status = "closed"; e.closed_at = datetime.utcnow(); s.add(e); s.commit()
    return {"ok": True}


# ── Больничный лист ──
class SickLeaveIn(BaseModel):
    encounter_id: Optional[int] = None
    number: str = ""
    opened_at: Optional[str] = None
    note: str = ""


class SickLeavePatch(BaseModel):
    expected_version: int
    status: Optional[str] = None              # extended | closed
    number: Optional[str] = None
    closed_at: Optional[str] = None
    note: Optional[str] = None


@router.post("/patients/{pid}/sick-leaves")
def open_sick_leave(pid: int, body: SickLeaveIn, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    sl = SickLeave(doctor_id=current_doctor_id(), patient_id=pid, encounter_id=body.encounter_id,
                   number=body.number, note=body.note,
                   opened_at=date.fromisoformat(body.opened_at) if body.opened_at else date.today())
    s.add(sl); s.commit(); s.refresh(sl)
    return dump(sl)


@router.get("/patients/{pid}/sick-leaves")
def list_sick_leaves(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    rows = s.exec(select(SickLeave).where(SickLeave.patient_id == pid)).all()
    rows.sort(key=lambda x: x.created_at, reverse=True)
    return dump_all(rows)


@router.patch("/sick-leaves/{sid}")
def update_sick_leave(sid: int, body: SickLeavePatch, s: Session = Depends(get_session)):
    sl = s.get(SickLeave, sid)
    if not sl or sl.doctor_id != current_doctor_id():
        raise HTTPException(404, "Больничный не найден")
    if sl.version != body.expected_version:
        raise HTTPException(409, "Больничный был изменён с другого устройства. Обновите и повторите.")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") in ("open", "extended", "closed"):
        sl.status = data["status"]
    if data.get("number") is not None:
        sl.number = data["number"]
    if data.get("note") is not None:
        sl.note = data["note"]
    if "closed_at" in data:
        sl.closed_at = date.fromisoformat(data["closed_at"]) if data["closed_at"] else None
    sl.version += 1
    s.add(sl); s.commit(); s.refresh(sl)
    return dump(sl)
