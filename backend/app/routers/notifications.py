from datetime import datetime
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..serialization import dump_all
from ..models import Notification
from ..services.notifications import generate

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(s: Session = Depends(get_session)):
    did = current_doctor_id()
    generate(s, did)                        # освежаем из текущего состояния
    rows = s.exec(select(Notification).where(Notification.doctor_id == did)).all()
    rows.sort(key=lambda n: (n.read, -(n.id or 0)))
    unread = sum(1 for n in rows if not n.read)
    return {"unread": unread, "items": dump_all(rows[:100])}


@router.post("/{nid}/read")
def mark_read(nid: int, s: Session = Depends(get_session)):
    n = s.get(Notification, nid)
    if n and n.doctor_id == current_doctor_id():
        n.read = True; s.add(n); s.commit()
    return {"ok": True}


@router.post("/read-all")
def read_all(s: Session = Depends(get_session)):
    for n in s.exec(select(Notification).where(
            Notification.doctor_id == current_doctor_id(), Notification.read == False)).all():
        n.read = True; s.add(n)
    s.commit()
    return {"ok": True}
