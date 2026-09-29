from datetime import datetime, timedelta
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..services.usage import meter
from ..services.telemetry import log_event
from ..models import Reminder
from ..schemas import ReminderIn, QuickReminderIn
from ..services.nlp import parse_reminder
from ..services.stt import transcribe

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


from ..serialization import dump as _dump
from pydantic import BaseModel
from .. import clock


class ReminderPatch(BaseModel):
    title: str | None = None
    due_at: str | None = None        # ISO дата/датавремя, "" или null — снять срок
    priority: int | None = None
    project: str | None = None
    kind: str | None = None
    repeat_unit: str | None = None
    repeat_interval: int | None = None


def _parse_due(v):
    """'' / None → снять срок; 'YYYY-MM-DD' → 09:00; полный ISO → как есть."""
    if v is None or v == "":
        return None
    if len(v) == 10:
        v = v + "T09:00:00"
    return datetime.fromisoformat(v)


@router.patch("/{rid}")
def update(rid: int, body: ReminderPatch, s: Session = Depends(get_session)):
    r = s.get(Reminder, rid)
    if not r or r.doctor_id != current_doctor_id():
        from fastapi import HTTPException
        raise HTTPException(404, "Задача не найдена")
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"]:
        r.title = data["title"]
    if "due_at" in data:
        r.due_at = _parse_due(data["due_at"])
    if "priority" in data and data["priority"]:
        r.priority = data["priority"]
    if "project" in data and data["project"]:
        r.project = data["project"]
    if "kind" in data and data["kind"]:
        r.kind = data["kind"]
    if "repeat_unit" in data and data["repeat_unit"] is not None:
        r.repeat_unit = data["repeat_unit"]     # "" — снять повтор
    if "repeat_interval" in data and data["repeat_interval"]:
        r.repeat_interval = max(1, int(data["repeat_interval"]))
    s.add(r); s.commit(); s.refresh(r)
    # срок мог измениться → пересчитываем будильники
    if "due_at" in data:
        from ..services.alerts import set_alerts
        set_alerts(s, r.doctor_id, "reminder", r.id, r.due_at, kind=r.kind)
    return _dump(r)


@router.delete("/{rid}")
def delete(rid: int, s: Session = Depends(get_session)):
    """Мягкое удаление: задача скрывается, но её можно вернуть («Отменить»)."""
    r = s.get(Reminder, rid)
    if r and r.doctor_id == current_doctor_id():
        r.status = "deleted"; s.add(r); s.commit()
        return {"ok": True, "id": r.id}
    return {"ok": True}


@router.post("/{rid}/restore")
def restore(rid: int, s: Session = Depends(get_session)):
    """Вернуть только что удалённую задачу."""
    r = s.get(Reminder, rid)
    if not r or r.doctor_id != current_doctor_id() or r.status != "deleted":
        raise HTTPException(404, "Задача не найдена")
    r.status = "open"; s.add(r); s.commit(); s.refresh(r)
    return _dump(r)


@router.get("")
def list_reminders(status: str = "open", s: Session = Depends(get_session)):
    rows = s.exec(select(Reminder).where(Reminder.doctor_id == current_doctor_id())).all()
    if status:
        rows = [r for r in rows if r.status == status]
    rows.sort(key=lambda r: (r.priority, r.due_at or datetime.max))
    return [_dump(r) for r in rows]


@router.get("/range")
def list_in_range(date_from: str, date_to: str, s: Session = Depends(get_session)):
    """Задачи со сроком в диапазоне [date_from, date_to] включительно (YYYY-MM-DD).
    Для календаря: задачи показываются рядом с приёмами. Без срока — не попадают."""
    d0 = datetime.fromisoformat(date_from)
    d1 = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59)
    rows = s.exec(select(Reminder).where(
        Reminder.doctor_id == current_doctor_id(),
        Reminder.due_at != None,                       # noqa: E711 — SQL IS NOT NULL
        Reminder.due_at >= d0, Reminder.due_at <= d1,
    )).all()
    rows = [r for r in rows if r.status == "open"]
    rows.sort(key=lambda r: r.due_at)
    out = []
    for r in rows:
        d = _dump(r)
        d["day"] = r.due_at.date().isoformat()
        d["time"] = r.due_at.strftime("%H:%M")
        out.append(d)
    return out


@router.post("")
def create(body: ReminderIn, s: Session = Depends(get_session)):
    r = Reminder(doctor_id=current_doctor_id(), **body.model_dump())
    s.add(r); s.commit(); s.refresh(r)
    # будильники по личным дефолтам врача для типа задачи (если у задачи есть срок)
    from ..services.alerts import set_alerts
    set_alerts(s, r.doctor_id, "reminder", r.id, r.due_at, kind=r.kind)
    dump = _dump(r)
    log_event(s, "reminder.created", {"kind": r.kind}, current_doctor_id())
    return dump


@router.post("/quick")
def quick(body: QuickReminderIn, s: Session = Depends(get_session)):
    """Естественный язык -> напоминание: срок, повтор, приоритет, метки."""
    p = parse_reminder(body.text)
    due = datetime.fromisoformat(p["due_at"]) if p["due_at"] else None
    r = Reminder(doctor_id=current_doctor_id(), patient_id=body.patient_id, title=p["title"],
                 due_at=due, kind=p["kind"], priority=p["priority"],
                 repeat_days=p["repeat_days"], labels=p["labels"],
                 project=p["project"], source="nl")
    s.add(r); s.commit(); s.refresh(r)
    return _dump(r)


@router.post("/voice")
async def voice(patient_id: int = Form(None), audio: UploadFile = File(None),
                audio_format: str = Form(""), s: Session = Depends(get_session)):
    meter(s, current_doctor_id(), "stt", detail="reminder")
    data = await audio.read() if audio else b""
    text = transcribe(data, audio_format)
    p = parse_reminder(text)
    due = datetime.fromisoformat(p["due_at"]) if p["due_at"] else None
    r = Reminder(doctor_id=current_doctor_id(), patient_id=patient_id, title=p["title"],
                 due_at=due, kind=p["kind"], priority=p["priority"],
                 repeat_days=p["repeat_days"], labels=p["labels"],
                 project=p["project"], source="voice")
    s.add(r); s.commit(); s.refresh(r)
    return {"transcript": text, "reminder": _dump(r)}


@router.post("/{rid}/done")
def done(rid: int, s: Session = Depends(get_session)):
    r = s.get(Reminder, rid)
    if not r:
        return {"ok": False}
    r.status = "done"; r.completed_at = clock.now(); s.add(r)
    next_r = None
    from ..services.recurrence import next_due
    base = r.due_at or clock.now()
    nd = next_due(base, r.repeat_unit, r.repeat_interval, r.repeat_days)
    if nd:
        next_r = Reminder(doctor_id=current_doctor_id(), patient_id=r.patient_id, title=r.title,
                          due_at=nd, kind=r.kind, priority=r.priority,
                          repeat_days=r.repeat_days, repeat_unit=r.repeat_unit,
                          repeat_interval=r.repeat_interval,
                          labels=r.labels, project=r.project, source=r.source)
        s.add(next_r)
    s.commit()
    if next_r:
        s.refresh(next_r)
        r.spawned_id = next_r.id; s.add(r); s.commit()
    return {"ok": True, "next": _dump(next_r)}


@router.post("/{rid}/reopen")
def reopen(rid: int, s: Session = Depends(get_session)):
    """Вернуть выполненную задачу в открытые («Отменить»). Если при выполнении был
    авто-создан следующий повтор — удаляем его, чтобы не задвоить."""
    r = s.get(Reminder, rid)
    if not r or r.doctor_id != current_doctor_id():
        raise HTTPException(404, "Задача не найдена")
    if r.spawned_id:
        nxt = s.get(Reminder, r.spawned_id)
        if nxt and nxt.status == "open":
            s.delete(nxt)
        r.spawned_id = None
    r.status = "open"; r.completed_at = None; s.add(r)
    s.commit()
    # восстановим будильники по актуальному сроку
    from ..services.alerts import set_alerts
    set_alerts(s, r.doctor_id, "reminder", r.id, r.due_at, kind=r.kind)
    return _dump(r)


@router.get("/projects")
def projects(s: Session = Depends(get_session)):
    rows = s.exec(select(Reminder).where(Reminder.doctor_id == current_doctor_id(),
                                         Reminder.status == "open")).all()
    seen = {}
    for r in rows:
        seen[r.project] = seen.get(r.project, 0) + 1
    return [{"project": k, "count": v} for k, v in seen.items()]


@router.post("/{rid}/postpone")
def postpone(rid: int, days: int = 1, s: Session = Depends(get_session)):
    r = s.get(Reminder, rid)
    if r:
        base = r.due_at or clock.now()
        r.due_at = base + timedelta(days=days)
        s.add(r); s.commit(); s.refresh(r)
    return _dump(r)
