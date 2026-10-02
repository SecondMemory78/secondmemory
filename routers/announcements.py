"""Объявления врачам: техработы, важное, новости.

Публикует админ, врач видит полосой в приложении и в уведомлениях.
Закрыть можно только если тип это разрешает: объявление о техработах
врач скрыть не должен.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import clock
from ..db import get_session
from ..deps import current_doctor_id
from ..models import Announcement, AnnouncementRead, Doctor

def _admin_auth(request: Request = None, x_admin_token: str = Header(default="")):
    """Тот же вход в админку, что и в остальных админских разделах."""
    from .analytics import _auth
    return _auth(request, x_admin_token)


router = APIRouter(prefix="/api/announcements", tags=["announcements"])
admin = APIRouter(prefix="/api/admin", tags=["admin"])

KINDS = {"maintenance": "Техработы", "important": "Важно", "news": "Новость"}

# Заготовки, чтобы не писать текст каждый раз с нуля
TEMPLATES = [
    {"code": "planned", "kind": "maintenance", "dismissible": False,
     "title": "Плановые технические работы",
     "text": "{date} с {from_time} до {to_time} возможны перебои в работе сервиса. "
             "Данные не пострадают."},
    {"code": "fixed", "kind": "news", "dismissible": True,
     "title": "Сбой устранён",
     "text": "Работа сервиса восстановлена. Приносим извинения за неудобства."},
    {"code": "release", "kind": "news", "dismissible": True,
     "title": "Обновление",
     "text": "В приложении появились новые возможности. Подробности — в разделе «Ещё»."},
]


class AnnouncementIn(BaseModel):
    kind: str = "maintenance"              # maintenance | important | news
    title: str
    text: str = ""
    dismissible: bool = True               # можно ли врачу закрыть
    audience: str = "all"                  # all | selected
    doctor_ids: list[int] = []             # если audience = selected
    starts_at: str | None = None           # период показа (ISO), необязателен
    ends_at: str | None = None
    active: bool = True


def _visible_for(s: Session, doctor_id: int,
                 include_dismissed: bool = False) -> list[Announcement]:
    """Объявления, которые врач должен видеть прямо сейчас.

    include_dismissed=True — для списка уведомлений: там закрытые полосой
    объявления всё равно должны остаться, чтобы важное не потерялось.
    """
    now = clock.now()
    rows = s.exec(select(Announcement).where(Announcement.active == True)).all()  # noqa: E712
    dismissed = {r.announcement_id for r in s.exec(
        select(AnnouncementRead).where(AnnouncementRead.doctor_id == doctor_id)).all()}
    out = []
    for a in rows:
        if a.starts_at and a.starts_at > now:
            continue                                   # ещё не началось
        if a.ends_at and a.ends_at < now:
            continue                                   # срок вышел
        if a.audience == "selected":
            ids = {int(x) for x in a.doctor_ids.split(",") if x.strip().isdigit()}
            if doctor_id not in ids:
                continue
        if a.dismissible and a.id in dismissed and not include_dismissed:
            continue                                   # врач закрыл полосу
        out.append(a)
    out.sort(key=lambda a: ({"important": 0, "maintenance": 1, "news": 2}.get(a.kind, 3),
                            -(a.created_at.timestamp())))
    return out


def _view(a: Announcement) -> dict:
    return {"id": a.id, "kind": a.kind, "kind_label": KINDS.get(a.kind, a.kind),
            "title": a.title, "text": a.text, "dismissible": a.dismissible,
            "starts_at": a.starts_at.isoformat() if a.starts_at else None,
            "ends_at": a.ends_at.isoformat() if a.ends_at else None,
            "created_at": a.created_at.isoformat()}


@router.get("")
def my_announcements(s: Session = Depends(get_session)):
    """Что показать врачу сейчас."""
    return {"items": [_view(a) for a in _visible_for(s, current_doctor_id())]}


@router.post("/{aid}/dismiss")
def dismiss(aid: int, s: Session = Depends(get_session)):
    """Закрыть объявление. Неотключаемые (техработы) закрыть нельзя."""
    a = s.get(Announcement, aid)
    if not a:
        raise HTTPException(404, "Объявление не найдено")
    if not a.dismissible:
        raise HTTPException(400, "Это объявление нельзя скрыть")
    did = current_doctor_id()
    already = s.exec(select(AnnouncementRead).where(
        AnnouncementRead.announcement_id == aid,
        AnnouncementRead.doctor_id == did)).first()
    if not already:
        s.add(AnnouncementRead(announcement_id=aid, doctor_id=did)); s.commit()
    return {"ok": True}


# ── админская часть ─────────────────────────────────────────────────────────
def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        raise HTTPException(400, f"Неверная дата: {value}")


@admin.get("/announcements/templates")
def list_templates(_: None = Depends(_admin_auth)):
    """Заготовки текстов, чтобы не писать каждый раз заново."""
    return {"items": TEMPLATES, "kinds": KINDS}


@admin.get("/announcements")
def admin_list(_: None = Depends(_admin_auth), s: Session = Depends(get_session)):
    rows = s.exec(select(Announcement).order_by(Announcement.id.desc())).all()
    reads = s.exec(select(AnnouncementRead)).all()
    closed = {}
    for r in reads:
        closed[r.announcement_id] = closed.get(r.announcement_id, 0) + 1
    return {"items": [{**_view(a), "active": a.active, "audience": a.audience,
                       "doctor_ids": a.doctor_ids, "created_by": a.created_by,
                       "dismissed_count": closed.get(a.id, 0)} for a in rows]}


@admin.post("/announcements")
def admin_create(body: AnnouncementIn, _: None = Depends(_admin_auth),
                 s: Session = Depends(get_session)):
    if body.kind not in KINDS:
        raise HTTPException(400, "Неизвестный тип объявления")
    if not (body.title or "").strip():
        raise HTTPException(400, "Заголовок обязателен")
    if body.audience == "selected" and not body.doctor_ids:
        raise HTTPException(400, "Выберите, кому показать объявление")

    a = Announcement(
        kind=body.kind, title=body.title.strip(), text=(body.text or "").strip(),
        # техработы врач скрывать не должен — подстраховываем выбор админа
        dismissible=False if body.kind == "maintenance" else body.dismissible,
        audience=body.audience,
        doctor_ids=",".join(str(x) for x in body.doctor_ids) if body.audience == "selected" else "",
        starts_at=_parse_dt(body.starts_at), ends_at=_parse_dt(body.ends_at),
        active=body.active, created_by="admin",
    )
    if a.starts_at and a.ends_at and a.ends_at < a.starts_at:
        raise HTTPException(400, "Конец периода раньше начала")
    s.add(a); s.commit(); s.refresh(a)
    return _view(a)


@admin.post("/announcements/{aid}/stop")
def admin_stop(aid: int, _: None = Depends(_admin_auth), s: Session = Depends(get_session)):
    """Снять объявление вручную, не дожидаясь конца периода."""
    a = s.get(Announcement, aid)
    if not a:
        raise HTTPException(404, "Объявление не найдено")
    a.active = False; s.add(a); s.commit(); s.refresh(a)
    return {**_view(a), "active": a.active}


@admin.delete("/announcements/{aid}")
def admin_delete(aid: int, _: None = Depends(_admin_auth), s: Session = Depends(get_session)):
    a = s.get(Announcement, aid)
    if not a:
        raise HTTPException(404, "Объявление не найдено")
    for r in s.exec(select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == aid)).all():
        s.delete(r)
    s.delete(a); s.commit()
    return {"ok": True}


# ── доверенные источники: очередь и наполнение (админ) ──────────────────────
class SourceResultIn(BaseModel):
    query: str
    quote: str = ""
    url: str


@admin.get("/sources/pending")
def sources_pending(_: None = Depends(_admin_auth), s: Session = Depends(get_session)):
    """Запросы врачей, по которым ещё не было проверки источников."""
    from ..services.sources import pending
    return {"items": pending(s)}


@admin.post("/sources/result")
def sources_save(body: SourceResultIn, _: None = Depends(_admin_auth),
                 s: Session = Depends(get_session)):
    """Сохранить проверенную цитату со ссылкой. Ссылка — только из списка."""
    from ..services.sources import save_result
    try:
        return save_result(s, body.query, quote=body.quote, url=body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
