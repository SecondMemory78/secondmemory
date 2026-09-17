"""Поддержка. Модель как в образце: одно открытое обращение (thread),
закрытые остаются в истории; флаг from_staff разделяет стороны; read_at даёт
непрочитанные. Адаптировано под наш стек (SQLModel, врач вместо tenant)."""
from datetime import datetime
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import require_admin
from ..models import SupportThread, SupportMessage, Doctor

STAFF_NAME = "Поддержка"


class MessageIn(BaseModel):
    body: str


def _open_thread(s: Session, doctor_id: int, first_body: str) -> SupportThread:
    t = s.exec(select(SupportThread).where(SupportThread.doctor_id == doctor_id,
                                           SupportThread.status == "open")).first()
    if not t:
        t = SupportThread(doctor_id=doctor_id, status="open",
                          subject=first_body.strip().splitlines()[0][:120] if first_body else "")
        s.add(t); s.commit(); s.refresh(t)
    return t


def _thread_dto(s: Session, t: SupportThread):
    msgs = s.exec(select(SupportMessage).where(SupportMessage.thread_id == t.id)).all()
    msgs.sort(key=lambda m: m.created_at)
    return {"id": t.id, "status": t.status, "subject": t.subject,
            "created_at": t.created_at.isoformat(),
            "messages": [m.model_dump() for m in msgs]}


# ===================== сторона врача =====================
doctor = APIRouter(prefix="/api/support", tags=["support"])


@doctor.get("/thread")
def current_thread(s: Session = Depends(get_session)):
    t = s.exec(select(SupportThread).where(SupportThread.doctor_id == current_doctor_id(),
                                           SupportThread.status == "open")).first()
    if not t:
        return {"thread": None, "unread": 0}
    dto = _thread_dto(s, t)
    unread = sum(1 for m in dto["messages"] if m["from_staff"] and not m["read_at"])
    return {"thread": dto, "unread": unread}


@doctor.post("/message")
def send(body: MessageIn, s: Session = Depends(get_session)):
    t = _open_thread(s, current_doctor_id(), body.body)
    m = SupportMessage(doctor_id=current_doctor_id(), thread_id=t.id, author_name="Врач",
                       from_staff=False, body=body.body)
    s.add(m); s.commit()
    # уведомляем поддержку о новом обращении: письмо (если настроено) + push админ-каналу
    import os
    from ..services.email import send_email
    from ..services.push import push_to_admin
    staff = os.getenv("SUPPORT_EMAIL", "")
    if staff:
        d = s.get(Doctor, current_doctor_id())
        send_email(staff, "Новое обращение в поддержку — Вторая память",
                   f"Врач: {d.full_name if d else current_doctor_id()}\n"
                   f"Обращение: {body.body[:500]}\n\nОткройте админ-панель для ответа.")
    push_to_admin(s, "support", "Поддержка", "Новое обращение от врача — откройте админ-панель")
    return _thread_dto(s, t)


@doctor.post("/read")
def mark_read(s: Session = Depends(get_session)):
    t = s.exec(select(SupportThread).where(SupportThread.doctor_id == current_doctor_id(),
                                           SupportThread.status == "open")).first()
    if t:
        for m in s.exec(select(SupportMessage).where(SupportMessage.thread_id == t.id,
                                                     SupportMessage.from_staff == True)).all():
            if not m.read_at:
                m.read_at = datetime.utcnow(); s.add(m)
        s.commit()
    return {"ok": True}


@doctor.get("/history")
def history(s: Session = Depends(get_session)):
    rows = s.exec(select(SupportThread).where(SupportThread.doctor_id == current_doctor_id())).all()
    rows.sort(key=lambda t: t.created_at, reverse=True)
    out = []
    for t in rows:
        msgs = s.exec(select(SupportMessage).where(SupportMessage.thread_id == t.id)).all()
        msgs.sort(key=lambda m: m.created_at)
        last = msgs[-1] if msgs else None
        out.append({"id": t.id, "status": t.status, "subject": t.subject,
                    "created_at": t.created_at.isoformat(),
                    "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    "preview": last.body[:120] if last else ""})
    return out


@doctor.get("/threads/{tid}/messages")
def thread_messages_doctor(tid: int, s: Session = Depends(get_session)):
    """Сообщения конкретного обращения врача. 404 (а не 403), если не его —
    как в правиле изоляции: чужой не должен даже узнать, что обращение есть."""
    t = s.get(SupportThread, tid)
    if not t or t.doctor_id != current_doctor_id():
        raise HTTPException(404, "Обращение не найдено")
    return _thread_dto(s, t)


# ===================== сторона поддержки (админ) =====================
staff = APIRouter(prefix="/api/admin/support", tags=["admin-support"],
                  dependencies=[Depends(require_admin)])


@staff.get("/threads")
def threads(s: Session = Depends(get_session)):
    rows = s.exec(select(SupportThread)).all()
    out = []
    for t in rows:
        msgs = s.exec(select(SupportMessage).where(SupportMessage.thread_id == t.id)).all()
        msgs.sort(key=lambda m: m.created_at)
        last = msgs[-1] if msgs else None
        unread = sum(1 for m in msgs if not m.from_staff and not m.read_at)
        out.append({"id": t.id, "doctor_id": t.doctor_id, "status": t.status,
                    "subject": t.subject, "unread": unread,
                    "last": last.body[:80] if last else "",
                    "created_at": t.created_at.isoformat()})
    out.sort(key=lambda x: (x["status"] != "open", x["created_at"]), reverse=False)
    return out


@staff.get("/threads/{tid}")
def thread_messages(tid: int, s: Session = Depends(get_session)):
    t = s.get(SupportThread, tid)
    if not t:
        return {"thread": None}
    # пометить сообщения врача прочитанными поддержкой
    for m in s.exec(select(SupportMessage).where(SupportMessage.thread_id == tid,
                                                 SupportMessage.from_staff == False)).all():
        if not m.read_at:
            m.read_at = datetime.utcnow(); s.add(m)
    s.commit()
    return _thread_dto(s, t)


@staff.post("/threads/{tid}/reply")
def reply(tid: int, body: MessageIn, s: Session = Depends(get_session)):
    t = s.get(SupportThread, tid)
    if not t:
        return {"ok": False}
    m = SupportMessage(doctor_id=t.doctor_id, thread_id=tid, author_name=STAFF_NAME,
                       from_staff=True, body=body.body)
    s.add(m); s.commit()
    # уведомление врачу об ответе (в приложении + push)
    from ..models import Notification
    from ..services.push import push_to_doctor
    s.add(Notification(doctor_id=t.doctor_id, kind="support", level="info",
                       text="Поддержка ответила вам", dedup_key=f"support-reply:{m.id}"))
    s.commit()
    push_to_doctor(s, t.doctor_id, "support", "Поддержка", "Поддержка ответила вам", url="/support")
    return _thread_dto(s, t)


@staff.post("/threads/{tid}/close")
def close(tid: int, s: Session = Depends(get_session)):
    t = s.get(SupportThread, tid)
    if t:
        t.status = "closed"; t.closed_at = datetime.utcnow(); s.add(t); s.commit()
    return {"ok": True}
