"""Шаблоны приёмов: встроенные T01–T12 + пользовательские наборы врача."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..models import VisitTemplate
from ..reference.visit_templates import all_templates, get_template

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _builtin_view(t):
    return {"code": t["code"], "name": t["name"], "category": t["category"], "builtin": True,
            "additional": t["additional"], "exam_docs": t["exam_docs"], "plan": t["plan"]}


def _custom_view(t: VisitTemplate):
    return {"code": f"custom:{t.id}", "id": t.id, "name": t.name, "category": t.category,
            "builtin": False, "based_on": t.based_on, "version": t.version,
            "additional": t.additional, "exam_docs": t.exam_docs, "plan": t.plan}


@router.get("")
def list_templates(s: Session = Depends(get_session)):
    """Все шаблоны: встроенные (сгруппированы по категориям) + личные врача."""
    builtin = [_builtin_view(t) for t in all_templates()]
    mine = [_custom_view(t) for t in s.exec(select(VisitTemplate).where(
        VisitTemplate.doctor_id == current_doctor_id())).all()]
    return {"builtin": builtin, "custom": mine}


@router.get("/{code}")
def get_one(code: str, s: Session = Depends(get_session)):
    if code.startswith("custom:"):
        t = s.get(VisitTemplate, int(code.split(":")[1]))
        if not t or t.doctor_id != current_doctor_id():
            raise HTTPException(404, "Шаблон не найден")
        return _custom_view(t)
    t = get_template(code)
    if not t:
        raise HTTPException(404, "Шаблон не найден")
    return _builtin_view(t)


class TemplateIn(BaseModel):
    name: str
    category: str = "Мои шаблоны"
    based_on: str = ""
    additional: str = ""
    exam_docs: str = ""
    plan: str = ""


@router.post("")
def save_template(body: TemplateIn, s: Session = Depends(get_session)):
    """Сохранить свой шаблон (можно на основе встроенного — based_on=T0x)."""
    t = VisitTemplate(doctor_id=current_doctor_id(), name=body.name, category=body.category,
                      based_on=body.based_on, additional=body.additional,
                      exam_docs=body.exam_docs, plan=body.plan)
    s.add(t); s.commit(); s.refresh(t)
    return _custom_view(t)


class TemplatePatch(BaseModel):
    expected_version: int
    name: str | None = None
    additional: str | None = None
    exam_docs: str | None = None
    plan: str | None = None


@router.patch("/custom/{tid}")
def update_template(tid: int, body: TemplatePatch, s: Session = Depends(get_session)):
    t = s.get(VisitTemplate, tid)
    if not t or t.doctor_id != current_doctor_id():
        raise HTTPException(404, "Шаблон не найден")
    if t.version != body.expected_version:
        raise HTTPException(409, "Шаблон изменён с другого устройства. Обновите и повторите.")
    data = body.model_dump(exclude_unset=True)
    for f in ("name", "additional", "exam_docs", "plan"):
        if data.get(f) is not None:
            setattr(t, f, data[f])
    t.version += 1
    s.add(t); s.commit(); s.refresh(t)
    return _custom_view(t)


@router.delete("/custom/{tid}")
def delete_template(tid: int, s: Session = Depends(get_session)):
    t = s.get(VisitTemplate, tid)
    if t and t.doctor_id == current_doctor_id():
        s.delete(t); s.commit()
    return {"ok": True}
