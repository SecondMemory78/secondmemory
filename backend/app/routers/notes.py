"""Заметки врача.

Два вида, намеренно раздельные:
  • «Мои заметки» (DoctorNote) — личные, без пациента. Полный CRUD.
  • «Все заметки» — сквозной список Note по ВСЕМ своим пациентам, только для
    чтения и перехода в карту: редактировать заметку пациента нужно в его карте,
    где виден контекст (приём, диагнозы, согласие).
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id, get_owned_patient
from .. import clock
from ..models import DoctorNote, Note, Patient

router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteIn(BaseModel):
    text: str = ""
    title: str = ""
    folder: str = ""
    checklist: list | None = None       # [{text, done}]
    drawing: str | None = None          # PNG строкой data:; None — не меняем
    pinned: bool = False
    source: str = "typed"


# Набросок весит десятки килобайт; полмегабайта — это уже не схема, а чья-то
# фотография, и в текстовом поле ей не место.
MAX_DRAWING = 512 * 1024


def _check_drawing(value) -> str:
    if not value:
        return ""
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        raise HTTPException(400, "Рисунок принимается только как PNG")
    if len(value) > MAX_DRAWING:
        raise HTTPException(400, "Рисунок слишком большой — упростите схему")
    return value


def _title_of(n: DoctorNote) -> str:
    """Заголовок. Не вписали — берём первую строку: список без названий
    через месяц превращается в стену текста."""
    if (n.title or "").strip():
        return n.title.strip()
    first = (n.text or "").strip().split("\n", 1)[0].strip()
    return first[:60] or "Без названия"


def _dump(n: DoctorNote) -> dict:
    import json
    try:
        checklist = json.loads(n.checklist or "[]")
    except Exception:
        checklist = []
    return {"id": n.id, "title": _title_of(n), "title_raw": n.title or "",
            "text": n.text, "folder": n.folder or "",
            "checklist": checklist,
            "checklist_done": sum(1 for x in checklist if x.get("done")),
            "checklist_total": len(checklist),
            "patient_id": n.patient_id,
            "drawing": n.drawing or "",
            "has_drawing": bool(n.drawing),
            "pinned": n.pinned, "source": n.source,
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
    import json
    text = (body.text or "").strip()
    checklist = body.checklist or []
    # Пустой считается заметка без текста, заголовка И пунктов: заметка может
    # быть одним только списком дел.
    drawing = _check_drawing(body.drawing)
    if not text and not (body.title or "").strip() and not checklist and not drawing:
        raise HTTPException(400, "Пустая заметка")
    n = DoctorNote(doctor_id=current_doctor_id(), text=text,
                   title=(body.title or "").strip(), folder=(body.folder or "").strip(),
                   checklist=json.dumps(checklist, ensure_ascii=False),
                   drawing=drawing,
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
    import json
    n = _own_note(s, nid)
    text = (body.text or "").strip()
    checklist = body.checklist if body.checklist is not None else json.loads(n.checklist or "[]")
    drawing = _check_drawing(body.drawing) if body.drawing is not None else (n.drawing or "")
    if not text and not (body.title or "").strip() and not checklist and not drawing:
        raise HTTPException(400, "Пустая заметка")
    n.text = text
    n.title = (body.title or "").strip()
    n.folder = (body.folder or "").strip()
    n.checklist = json.dumps(checklist, ensure_ascii=False)
    n.drawing = drawing
    n.pinned = body.pinned
    n.updated_at = clock.now()
    s.add(n); s.commit(); s.refresh(n)
    return _dump(n)


@router.get("/my/folders")
def my_folders(s: Session = Depends(get_session)):
    """Папки, которые врач уже заводил. Отдельного справочника нет намеренно:
    папка — просто слово, и заставлять заводить её заранее незачем."""
    rows = s.exec(select(DoctorNote).where(
        DoctorNote.doctor_id == current_doctor_id(),
        DoctorNote.deleted_at == None)).all()                    # noqa: E711
    folders = {}
    for n in rows:
        if (n.folder or "").strip():
            folders[n.folder] = folders.get(n.folder, 0) + 1
    return {"items": [{"name": k, "count": v} for k, v in sorted(folders.items())]}


# ВАЖНО: объявлять ПОСЛЕ /my/folders. Иначе путь «folders» подходит под
# шаблон {nid}, FastAPI пытается привести его к числу и отвечает 422.
@router.get("/my/{nid}")
def get_my_note(nid: int, s: Session = Depends(get_session)):
    return _dump(_own_note(s, nid))


class ToTaskIn(BaseModel):
    index: int                      # какой пункт списка превращаем
    due_at: Optional[datetime] = None


@router.post("/my/{nid}/checklist/to-task")
def checklist_item_to_task(nid: int, body: ToTaskIn, s: Session = Depends(get_session)):
    """Пункт списка → задача.

    Пункты списка НЕ являются задачами сами по себе: иначе список просроченного
    забьётся пунктами без срока, и врач перестанет ему доверять. Задачей пункт
    становится здесь, осознанно и со сроком.

    Сам пункт остаётся в заметке и помечается ссылкой на задачу: иначе врач
    увидит его снова и заведёт второй раз.
    """
    import json
    from ..models import Reminder
    n = _own_note(s, nid)
    items = json.loads(n.checklist or "[]")
    if not 0 <= body.index < len(items):
        raise HTTPException(404, "Пункт не найден")
    item = items[body.index]
    if item.get("reminder_id"):
        raise HTTPException(409, "Из этого пункта задача уже создана")
    title = (item.get("text") or "").strip()
    if not title:
        raise HTTPException(400, "Пустой пункт")

    r = Reminder(doctor_id=current_doctor_id(), title=title, due_at=body.due_at,
                 kind="task", priority=2, source="note")
    s.add(r); s.commit(); s.refresh(r)

    items[body.index] = {**item, "reminder_id": r.id}
    n.checklist = json.dumps(items, ensure_ascii=False)
    n.updated_at = clock.now()
    s.add(n); s.commit(); s.refresh(n)
    return {"ok": True, "reminder_id": r.id, "note": _dump(n)}


class ToPatientIn(BaseModel):
    patient_id: int


@router.post("/my/{nid}/to-patient")
def note_to_patient(nid: int, body: ToPatientIn, s: Session = Depends(get_session)):
    """Перенести заметку в карту пациента.

    С этого момента она становится частью медицинской карты: попадает в
    выгрузку и в историю. Поэтому переносит врач осознанно — само ничего
    не привязывается.
    """
    from ..models import Note
    from ..services.visits import active_encounter_id
    n = _own_note(s, nid)
    patient = get_owned_patient(s, body.patient_id)

    text = ((n.title + "\n") if n.title else "") + (n.text or "")
    import json
    for it in json.loads(n.checklist or "[]"):
        mark = "[x]" if it.get("done") else "[ ]"
        text += f"\n{mark} {it.get('text', '')}"

    s.add(Note(patient_id=patient.id, encounter_id=active_encounter_id(s, patient.id),
               text=text.strip(), source="note"))
    n.patient_id = patient.id          # видно, что заметка уже перенесена
    n.updated_at = clock.now()
    s.add(n); s.commit()
    return {"ok": True, "patient_id": patient.id,
            "message": f"Заметка перенесена в карту: {patient.short_name}"}


@router.post("/my/{nid}/to-assistant")
def note_to_assistant(nid: int, s: Session = Depends(get_session)):
    """Отдать текст заметки разбору ассистента.

    Назначения и показатели из заметки получаются тем же механизмом, что из
    голосовой команды: одна логика на оба канала, иначе они разойдутся.
    Результат — предложение, как и везде.
    """
    from ..services.assistant import route_command
    n = _own_note(s, nid)
    text = (n.text or "").strip()
    if not text:
        raise HTTPException(400, "В заметке нет текста для разбора")
    return route_command(text, s, channel="note")


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
