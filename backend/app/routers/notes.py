"""Заметки врача.

Два вида, намеренно раздельные:
  • «Мои заметки» (DoctorNote) — личные, без пациента. Полный CRUD.
  • «Все заметки» — сквозной список Note по ВСЕМ своим пациентам, только для
    чтения и перехода в карту: редактировать заметку пациента нужно в его карте,
    где виден контекст (приём, диагнозы, согласие).
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from .. import clock
from ..models import DoctorNote, Note, Patient

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteIn(BaseModel):
    text: str
    pinned: bool = False
    source: str = "typed"


def _dump(n: DoctorNote) -> dict:
    return {"id": n.id, "text": n.text, "pinned": n.pinned, "source": n.source,
            "created_at": n.created_at.isoformat(), "updated_at": n.updated_at.isoformat()}


@router.get("/my")
def list_my_notes(q: str = "", s: Session = Depends(get_session)):
    """Мои заметки — закреплённые сверху, дальше свежие."""
    rows = s.exec(select(DoctorNote).where(DoctorNote.doctor_id == current_doctor_id())).all()
    rows = [n for n in rows if n.deleted_at is None]       # удалённые не показываем
    ql = (q or "").strip().lower()
    if ql:
        rows = [n for n in rows if ql in (n.text or "").lower()]
    rows.sort(key=lambda n: (not n.pinned, -(n.updated_at.timestamp())))
    return {"items": [_dump(n) for n in rows]}


@router.post("/my")
def create_my_note(body: NoteIn, s: Session = Depends(get_session)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустая заметка")
    n = DoctorNote(doctor_id=current_doctor_id(), text=text,
                   pinned=body.pinned, source=body.source)
    s.add(n); s.commit(); s.refresh(n)
    return _dump(n)


def _own_note(s: Session, nid: int, allow_deleted: bool = False) -> DoctorNote:
    n = s.get(DoctorNote, nid)
    if not n or n.doctor_id != current_doctor_id():   # чужая/несуществующая → 404
        raise HTTPException(404, "Заметка не найдена")
    if n.deleted_at is not None and not allow_deleted:
        raise HTTPException(404, "Заметка удалена")
    return n


@router.patch("/my/{nid}")
def update_my_note(nid: int, body: NoteIn, s: Session = Depends(get_session)):
    n = _own_note(s, nid)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустая заметка")
    n.text = text; n.pinned = body.pinned; n.updated_at = clock.now()
    s.add(n); s.commit(); s.refresh(n)
    return _dump(n)


@router.post("/my/{nid}/pin")
def toggle_pin(nid: int, s: Session = Depends(get_session)):
    n = _own_note(s, nid)
    n.pinned = not n.pinned; n.updated_at = clock.now()
    s.add(n); s.commit(); s.refresh(n)
    return _dump(n)


@router.delete("/my/{nid}")
def delete_my_note(nid: int, s: Session = Depends(get_session)):
    """Мягкое удаление: заметка скрывается, но её можно вернуть («Отменить»)."""
    n = _own_note(s, nid)
    n.deleted_at = clock.now(); s.add(n); s.commit()
    return {"ok": True, "id": n.id}


@router.post("/my/{nid}/restore")
def restore_my_note(nid: int, s: Session = Depends(get_session)):
    """Вернуть только что удалённую заметку."""
    n = _own_note(s, nid, allow_deleted=True)
    n.deleted_at = None; n.updated_at = clock.now()
    s.add(n); s.commit(); s.refresh(n)
    return _dump(n)


@router.get("/all")
def list_all_patient_notes(q: str = "", limit: int = Query(200, le=500),
                           s: Session = Depends(get_session)):
    """Сквозной список заметок по всем СВОИМ пациентам (только чтение)."""
    pats = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id())).all()
    by_id = {p.id: p for p in pats}
    if not by_id:
        return {"items": []}
    rows = s.exec(select(Note).where(Note.patient_id.in_(list(by_id.keys())))).all()
    ql = (q or "").strip().lower()
    out = []
    for n in rows:
        p = by_id.get(n.patient_id)
        if not p:
            continue
        name = " ".join(x for x in [p.last_name, p.first_name] if x)
        if ql and ql not in (n.text or "").lower() and ql not in name.lower():
            continue
        out.append({"id": n.id, "patient_id": n.patient_id, "patient_name": name,
                    "text": n.text, "source": n.source,
                    "created_at": n.created_at.isoformat()})
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": out[:limit]}
