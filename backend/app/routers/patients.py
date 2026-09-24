from datetime import date
from ..deps import current_doctor_id, get_owned_patient
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from ..db import get_session
from ..services.consent import require_consent
from ..services.visits import active_encounter_id
from ..models import Patient, Observation, AuditEvent, Note
from pydantic import BaseModel
from ..schemas import PatientIn, CohortQuery

router = APIRouter(prefix="/api/patients", tags=["patients"])  # MVP: один врач — своя база


def _audit(s: Session, entity_id, action, detail=""):
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="patient",
                     entity_id=entity_id, action=action, detail=detail))


@router.get("")
def list_patients(q: Optional[str] = None, s: Session = Depends(get_session)):
    stmt = select(Patient).where(Patient.doctor_id == current_doctor_id(),
                                 Patient.is_training == False)
    rows = [p for p in s.exec(stmt).all() if not (p.identity_status or "").startswith("merged_into")]
    if q:
        ql = q.lower()
        rows = [p for p in rows if ql in f"{p.last_name} {p.first_name} {p.middle_name}".lower()
                or ql in (p.diagnosis_code or "").lower()
                or ql in (p.diagnosis_text or "").lower()]
    return [_card(p) for p in rows]


@router.post("/check-identity")
def check_identity(body: PatientIn, mode: str = "manual", s: Session = Depends(get_session)):
    """Проверка личности до создания: вернёт похожих кандидатов/конфликты.
    Ничего не создаёт. Использует общие правила PAT."""
    from ..services.identity import resolve_identity
    q = body.model_dump()
    return resolve_identity(s, current_doctor_id(), q, mode=mode)


@router.post("")
def create_patient(body: PatientIn, s: Session = Depends(get_session)):
    """Создание пациента. Предупреждение о похожих — отдельным вызовом /check-identity
    (фронт делает его перед созданием и показывает диалог). Сам create не блокирует:
    решение о создании принимает врач."""
    data = body.model_dump()
    ext_system = data.pop("external_system", "")
    ext_value = data.pop("external_value", "")
    # неполные данные → карточка предварительная (identity_status=provisional)
    provisional = not (data.get("last_name") and data.get("first_name") and data.get("birth_date"))
    p = Patient(doctor_id=current_doctor_id(),
                identity_status="provisional" if provisional else "confirmed", **data)
    from ..services.identity import name_index_for
    p.name_index = name_index_for(p.last_name, p.first_name)
    s.add(p); s.commit(); s.refresh(p)
    if ext_system and ext_value:
        from ..models import PatientExternalId
        s.add(PatientExternalId(patient_id=p.id, system=ext_system, value=ext_value)); s.commit()
    _audit(s, p.id, "create", p.short_name); s.commit()
    return _card(p)


class MergeIn(BaseModel):
    keep_id: int
    merge_id: int


@router.post("/merge")
def merge_patients(body: MergeIn, s: Session = Depends(get_session)):
    """Объединение дублей (PAT-04): переносит все связи с merge_id на keep_id,
    пишет аудит, обратимо (merge_id помечается объединённым, не удаляется физически)."""
    from ..models import (Observation, Note, Prescription, SafetyItem, VisitProtocol,
                          Appointment, Reminder, PatientConsent, PatientDiagnosis,
                          SourceDocument, Encounter, PatientExternalId)
    did = current_doctor_id()
    keep = s.get(Patient, body.keep_id)
    merge = s.get(Patient, body.merge_id)
    if not keep or not merge or keep.doctor_id != did or merge.doctor_id != did:
        raise HTTPException(404, "Карточка не найдена")
    if keep.id == merge.id:
        raise HTTPException(400, "Нельзя объединить карточку саму с собой")
    moved = {}
    for model in (Observation, Note, Prescription, SafetyItem, VisitProtocol,
                  Appointment, Reminder, PatientConsent, PatientDiagnosis,
                  SourceDocument, Encounter, PatientExternalId):
        rows = s.exec(select(model).where(model.patient_id == merge.id)).all()
        for r in rows:
            r.patient_id = keep.id
            s.add(r)
        if rows:
            moved[model.__name__] = len(rows)
    # merge-карточку помечаем объединённой (обратимость: связь сохранена в аудите)
    merge.identity_status = f"merged_into:{keep.id}"
    s.add(merge)
    _audit(s, keep.id, "merge", f"объединено из #{merge.id}: {moved}")
    s.commit()
    return {"ok": True, "keep_id": keep.id, "merged_id": merge.id, "moved": moved}


@router.get("/{pid}")
def get_patient(pid: int, s: Session = Depends(get_session)):
    p = get_owned_patient(s, pid)               # чужой/несуществующий пациент → 404
    return _card(p)


@router.get("/{pid}/timeline")
def timeline(pid: int, s: Session = Depends(get_session)):
    """Динамика: по каждому параметру — упорядоченный ряд значений."""
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    obs = s.exec(select(Observation).where(Observation.patient_id == pid)).all()
    series = {}
    for o in obs:
        series.setdefault(o.parameter_code, []).append({
            "value_num": o.value_num, "value_text": o.value_text, "unit": o.unit,
            "date": o.effective_date.isoformat() if o.effective_date else None,
            "status": o.status, "id": o.id,
        })
    for code in series:
        series[code].sort(key=lambda x: x["date"] or "")
    return series


def _threshold_num(code: str):
    """Числовой порог параметра из справочника (первое число в текстовом пороге)."""
    import re
    from ..reference_data import parameters
    for p in parameters():
        if p["code"] == code and p.get("threshold"):
            m = re.search(r"(\d+[.,]?\d*)", p["threshold"])
            if m:
                return float(m.group(1).replace(",", ".")), p.get("name", code)
    return None, None


@router.get("/{pid}/integrity")
def integrity(pid: int, s: Session = Depends(get_session)):
    """Детерминированная проверка целостности карты (D-правила без ИИ). Только сигналы."""
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    from ..services.integrity import check_patient
    findings = check_patient(s, pid)
    return {"count": len(findings), "findings": findings}


@router.get("/{pid}/whats-new")
def whats_new(pid: int, s: Session = Depends(get_session)):
    """Сводка «что изменилось с прошлого раза» — из готовых данных, без ИИ.
    Только чтение: доступно и для просмотра (барьер согласия не нужен)."""
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    from ..models import Reminder
    from .. import clock
    now = clock.now()
    did = current_doctor_id()

    rems = s.exec(select(Reminder).where(Reminder.doctor_id == did,
                                         Reminder.patient_id == pid,
                                         Reminder.status == "open")).all()
    overdue = [{"id": r.id, "title": r.title,
                "days": max(0, (now - r.due_at).days)} for r in rems if r.due_at and r.due_at < now]
    open_tasks = len(rems)

    pending = s.exec(select(Observation).where(Observation.patient_id == pid,
                                               Observation.status == "pending")).all()

    # показатели выше порога (по последнему подтверждённому значению)
    obs = s.exec(select(Observation).where(Observation.patient_id == pid,
                                           Observation.status == "confirmed")).all()
    latest = {}
    for o in obs:
        if o.value_num is None:
            continue
        cur = latest.get(o.parameter_code)
        if not cur or (o.effective_date or date.min) >= (cur.effective_date or date.min):
            latest[o.parameter_code] = o
    alerts = []
    for code, o in latest.items():
        thr, name = _threshold_num(code)
        if thr is not None and o.value_num > thr:
            alerts.append({"code": code, "name": name or code, "value": o.value_num,
                           "unit": o.unit, "threshold": thr})

    # дата последней активности (показатель/заметка)
    dates = [o.effective_date for o in obs if o.effective_date]
    notes = s.exec(select(Note).where(Note.patient_id == pid)).all()
    note_dates = [n.created_at.date() for n in notes]
    last_activity = max(dates + note_dates) if (dates or note_dates) else None

    # открытые больничные (не привязаны к выписке → напоминаем закрыть)
    from ..models import SickLeave
    open_sl = s.exec(select(SickLeave).where(SickLeave.patient_id == pid,
                                             SickLeave.status.in_(["open", "extended"]))).all()

    return {
        "overdue": overdue,
        "open_tasks": open_tasks,
        "pending_count": len(pending),
        "alerts": alerts,
        "open_sick_leaves": len(open_sl),
        "last_activity": last_activity.isoformat() if last_activity else None,
        "has_news": bool(overdue or pending or alerts or open_sl),
    }


@router.get("/{pid}/notes")
def notes(pid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    rows = s.exec(select(Note).where(Note.patient_id == pid)).all()
    return sorted([n.model_dump() for n in rows], key=lambda x: x["created_at"], reverse=True)


@router.post("/{pid}/notes")
def add_note(pid: int, text: str = Query(...), source: str = "typed",
             encounter_id: int = Query(default=None),
             s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # сначала владелец (чужой/нет → 404), потом согласие
    require_consent(s, pid)
    from ..services.visits import resolve_encounter, open_encounters
    eid, ambiguous = resolve_encounter(s, pid, encounter_id)
    if ambiguous:
        raise HTTPException(409, {"ambiguous": True, "message": "К какому эпизоду отнести запись?",
                                  "episodes": [{"id": e.id, "type": e.type, "reason": e.reason,
                                                "ward": e.ward} for e in open_encounters(s, pid)]})
    n = Note(patient_id=pid, encounter_id=eid, text=text, source=source)
    s.add(n); s.commit(); s.refresh(n)
    return n.model_dump()


@router.patch("/{pid}/notes/{nid}")
def edit_note(pid: int, nid: int, text: str = Query(...), s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    require_consent(s, pid)
    n = s.get(Note, nid)
    if not n or n.patient_id != pid:
        raise HTTPException(404, "Заметка не найдена")
    n.text = text; s.add(n); s.commit(); s.refresh(n)
    return n.model_dump()


@router.delete("/{pid}/notes/{nid}")
def delete_note(pid: int, nid: int, s: Session = Depends(get_session)):
    get_owned_patient(s, pid)                    # чужой/несуществующий пациент → 404
    n = s.get(Note, nid)
    if n and n.patient_id == pid:
        s.delete(n); s.commit()
    return {"ok": True}


@router.post("/{pid}/notes/{nid}/task")
def note_to_task(pid: int, nid: int, due_at: str = Query(default=""), s: Session = Depends(get_session)):
    """Сделать из заметки задачу: создаёт напоминание с текстом заметки, привязанное к пациенту."""
    from ..models import Reminder
    from datetime import datetime
    p = get_owned_patient(s, pid)               # чужой/несуществующий пациент → 404
    n = s.get(Note, nid)
    if not n or n.patient_id != pid:
        raise HTTPException(404, "Заметка не найдена")
    due = None
    if due_at:
        due = datetime.fromisoformat(due_at + "T09:00:00" if len(due_at) == 10 else due_at)
    title = n.text if len(n.text) <= 120 else n.text[:117] + "…"
    r = Reminder(doctor_id=current_doctor_id(), title=title, patient_id=pid,
                 due_at=due, project="Из заметок", kind="task",
                 labels=(p.last_name if p else ""))
    s.add(r); s.commit(); s.refresh(r)
    return r.model_dump()


class PatientPatch(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    birth_date: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/{pid}")
def edit_patient(pid: int, body: PatientPatch, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p or p.doctor_id != current_doctor_id():
        raise HTTPException(404, "Пациент не найден")
    data = body.model_dump(exclude_unset=True)
    for f in ("last_name", "first_name", "middle_name", "phone"):
        if data.get(f) is not None:
            setattr(p, f, data[f])
    if data.get("birth_date"):
        from datetime import date as _date
        p.birth_date = _date.fromisoformat(data["birth_date"])
    if data.get("last_name") is not None or data.get("first_name") is not None:
        from ..services.identity import name_index_for
        p.name_index = name_index_for(p.last_name, p.first_name)   # ФИО изменилось → индекс пересчитать
    s.add(p); s.commit(); s.refresh(p)
    return p.model_dump()


@router.post("/cohort")
def cohort(body: CohortQuery, s: Session = Depends(get_session)):
    """Срез по картотеке: диагноз + порог показателя + возраст."""
    pts = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id(),
                                       Patient.is_training == False)).all()
    result = []
    today = date.today()
    for p in pts:
        if body.diagnosis_code and body.diagnosis_code.lower() not in (p.diagnosis_code or "").lower():
            continue
        if body.age_min or body.age_max:
            if not p.birth_date:
                continue
            age = today.year - p.birth_date.year
            if body.age_min and age < body.age_min:
                continue
            if body.age_max and age > body.age_max:
                continue
        key_val = None
        if body.parameter_code:
            obs = s.exec(select(Observation).where(
                Observation.patient_id == p.id,
                Observation.parameter_code == body.parameter_code,
                Observation.status == "confirmed",
            )).all()
            obs = [o for o in obs if o.value_num is not None]
            if not obs:
                continue
            latest = max(obs, key=lambda o: o.effective_date or date.min)
            key_val = latest.value_num
            if body.op and body.threshold is not None:
                ok = {">": key_val > body.threshold, "<": key_val < body.threshold,
                      ">=": key_val >= body.threshold, "<=": key_val <= body.threshold}.get(body.op, True)
                if not ok:
                    continue
        card = _card(p); card["key_value"] = key_val
        result.append(card)
    return result


def _card(p: Patient):
    age = None
    if p.birth_date:
        age = date.today().year - p.birth_date.year
    return {
        "id": p.id, "last_name": p.last_name, "first_name": p.first_name,
        "middle_name": p.middle_name, "short_name": p.short_name,
        "birth_date": p.birth_date.isoformat() if p.birth_date else None,
        "age": age, "sex": p.sex, "phone": p.phone,
        "diagnosis_code": p.diagnosis_code, "diagnosis_text": p.diagnosis_text,
    }
