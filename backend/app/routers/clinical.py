from typing import List
from ..deps import current_doctor_id, get_owned_patient
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from ..db import get_session
from ..services.visits import active_encounter_id
from ..services.telemetry import log_event
from ..services.dose_check import dose_reference
from ..services.consent import consent_ok, require_consent
from ..models import Observation, SafetyItem, Prescription, AuditEvent
from ..schemas import ObservationIn, SafetyIn, PrescriptionIn, PrescriptionPatch
from .. import clock
from ..services.allergy import check_conflict

router = APIRouter(prefix="/api", tags=["clinical"])

# Согласие 152-ФЗ сюда НЕ входит: это юридический документ с подписью и своим
# оформлением, а не клинический пункт «неизвестно / нет / есть». Второй
# источник правды о согласии опасен — он мог противоречить реальному статусу.
SAFETY_KINDS = ["allergy", "anticoag", "surgery", "chronic"]


# ---- наблюдения (значения показателей) ----
@router.post("/patients/{pid}/observations")
def add_observation(pid: int, body: ObservationIn, encounter_id: int = None,
                    s: Session = Depends(get_session)):
    require_consent(s, pid)
    from ..services.visits import resolve_encounter, open_encounters
    eid, ambiguous = resolve_encounter(s, pid, encounter_id)
    if ambiguous:
        raise HTTPException(409, {"ambiguous": True, "message": "К какому эпизоду отнести показатель?",
                                  "episodes": [{"id": e.id, "type": e.type, "reason": e.reason,
                                                "ward": e.ward} for e in open_encounters(s, pid)]})
    o = Observation(patient_id=pid, encounter_id=eid, **body.model_dump())
    s.add(o); s.commit(); s.refresh(o)
    dump = o.model_dump()          # снимок ДО следующего commit: иначе объект
                                   # «истекает» и ответ уходит пустым
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=o.id,
                     action="create", detail=f"{o.parameter_code}={o.value_num} [{o.status}]"))
    s.commit()
    return dump


def _owned_observation(s: Session, oid: int) -> Observation:
    """Значение своего пациента. Без этой проверки чужое значение можно было
    подтвердить по одному id — тот же класс дыры, что мы уже закрывали."""
    o = s.get(Observation, oid)
    if not o:
        raise HTTPException(404, "Значение не найдено")
    get_owned_patient(s, o.patient_id)          # чужой пациент → 404
    return o


@router.post("/observations/{oid}/confirm")
def confirm_observation(oid: int, s: Session = Depends(get_session)):
    o = _owned_observation(s, oid)
    o.status = "confirmed"; s.add(o)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=o.id,
                     action="confirm", detail="врач подтвердил извлечённое значение"))
    s.commit(); s.refresh(o)
    return o.model_dump()


@router.post("/observations/{oid}/reject")
def reject_observation(oid: int, s: Session = Depends(get_session)):
    """Отклонить распознанное значение: врач не согласен с тем, что извлёк ИИ.
    Не удаляем — помечаем, чтобы осталась история и значение не висело в работе."""
    o = _owned_observation(s, oid)
    o.status = "rejected"; s.add(o)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=o.id,
                     action="reject", detail="врач отклонил извлечённое значение"))
    s.commit(); s.refresh(o)
    return o.model_dump()


@router.delete("/observations/{oid}")
def delete_observation(oid: int, s: Session = Depends(get_session)):
    """Удалить значение совсем — когда оно просто ошибочное и не нужно в истории."""
    o = _owned_observation(s, oid)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="observation", entity_id=oid,
                     action="delete", detail=f"{o.parameter_code}"))
    s.delete(o); s.commit()
    return {"ok": True}


# ---- блок безопасности ----
@router.get("/patients/{pid}/safety")
def get_safety(pid: int, s: Session = Depends(get_session)):
    rows = {r.kind: r for r in s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid)).all()}
    out = []
    for k in SAFETY_KINDS:
        r = rows.get(k)
        out.append({"kind": k, "state": r.state if r else "unknown", "detail": r.detail if r else ""})
    complete = all(x["state"] != "unknown" for x in out)
    return {"items": out, "complete": complete}


@router.put("/patients/{pid}/safety")
def set_safety(pid: int, body: SafetyIn, s: Session = Depends(get_session)):
    r = s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid,
                                        SafetyItem.kind == body.kind)).first()
    if r:
        r.state, r.detail = body.state, body.detail
    else:
        r = SafetyItem(patient_id=pid, kind=body.kind, state=body.state, detail=body.detail)
    s.add(r)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="safety", entity_id=pid,
                     action="update", detail=f"{body.kind}={body.state}"))
    s.commit()
    return {"kind": r.kind, "state": r.state, "detail": r.detail}


# ---- назначения (с проверкой аллергий) ----
@router.post("/patients/{pid}/prescriptions")
def prescribe(pid: int, body: PrescriptionIn, s: Session = Depends(get_session)):
    if not consent_ok(s, pid):
        raise HTTPException(403, "Нет согласия на обработку ПДн — приём вести нельзя. Оформите согласие.")
    # проверка аллергий имеет смысл только для лекарственных назначений
    conflict = None
    if (body.category or "drug") == "drug":
        allergies = s.exec(select(SafetyItem).where(SafetyItem.patient_id == pid,
                                                    SafetyItem.kind == "allergy")).all()
        conflict = check_conflict(body.drug_name, allergies)
    # Система не блокирует: если конфликт есть и нет причины — вернём предупреждение.
    if conflict and not body.override_reason:
        return {"conflict": True, "saved": False, **conflict}
    # Предложение ИИ не становится действующим назначением без врача (спец., п.18)
    is_ai_suggestion = body.source == "ai_suggested"
    p = Prescription(patient_id=pid, encounter_id=active_encounter_id(s, pid),
                     drug_name=body.drug_name, dose=body.dose,
                     regimen=body.regimen, conflict_flag=bool(conflict),
                     override_reason=body.override_reason,
                     category=body.category or "drug", indication=body.indication,
                     instruction=body.instruction, route=body.route,
                     frequency=body.frequency, duration=body.duration,
                     starts_on=body.starts_on, control=body.control,
                     control_date=body.control_date, source=body.source or "doctor",
                     priority=body.priority or "normal",
                     confirmed=not is_ai_suggestion,
                     status="planned" if is_ai_suggestion else (body.status or "active"))
    s.add(p); s.commit(); s.refresh(p)
    detail = f"{p.drug_name}"
    if conflict:
        detail += f" | {conflict['message']} | ПЕРЕОПРЕДЕЛЕНО: {body.override_reason}"
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="prescription", entity_id=p.id,
                     action="create", detail=detail))
    s.commit()
    new_id = p.id
    log_event(s, "prescription.created", {"conflict": bool(conflict)}, current_doctor_id())
    dose_ref = (dose_reference(body.drug_name, body.dose)
                if (body.category or "drug") == "drug"
                else {"has_reference": False})
    return {"conflict": bool(conflict), "saved": True, "id": new_id,
            "dose_reference": dose_ref if dose_ref["has_reference"] else None,
            **(conflict or {})}


@router.get("/patients/{pid}/prescriptions")
def list_prescriptions(pid: int, s: Session = Depends(get_session)):
    """Назначения пациента (активные и отменённые — историю не прячем)."""
    get_owned_patient(s, pid)                 # чужой/несуществующий пациент → 404
    rows = s.exec(select(Prescription).where(Prescription.patient_id == pid)
                  .order_by(Prescription.status.desc(), Prescription.id.desc())).all()
    # единый вид записи — иначе новые поля не доходят до интерфейса
    return {"items": [{**_presc_view(r),
                       "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None}
                      for r in rows]}


@router.post("/prescriptions/{rx_id}/cancel")
def cancel_prescription(rx_id: int, s: Session = Depends(get_session)):
    """Отменить назначение (не удаляем — помечаем cancelled, история сохраняется)."""
    from .. import clock
    r = s.get(Prescription, rx_id)
    if not r:
        raise HTTPException(404, "Назначение не найдено")
    get_owned_patient(s, r.patient_id)        # владелец пациента → 404 для чужого
    if r.status == "cancelled":
        raise HTTPException(409, "Назначение уже отменено")
    r.status = "cancelled"
    r.cancelled_at = clock.now()
    s.add(r)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="prescription",
                     entity_id=r.id, action="cancel", detail=r.drug_name))
    s.commit()
    return {"ok": True, "id": r.id, "status": r.status}


def _presc_owned(s: Session, pid: int, rid: int) -> Prescription:
    get_owned_patient(s, pid)                     # чужой пациент → 404
    p = s.get(Prescription, rid)
    if not p or p.patient_id != pid:
        raise HTTPException(404, "Назначение не найдено")
    return p


def _snapshot(p: Prescription) -> str:
    """Прежняя версия назначения — для истории изменений."""
    import json
    keep = ("drug_name", "dose", "regimen", "category", "indication", "instruction",
            "route", "frequency", "duration", "control", "priority", "status",
            "cancel_reason", "effect", "confirmed")
    data = {k: getattr(p, k) for k in keep}
    data["starts_on"] = p.starts_on.isoformat() if p.starts_on else None
    data["control_date"] = p.control_date.isoformat() if p.control_date else None
    return json.dumps(data, ensure_ascii=False)


@router.patch("/patients/{pid}/prescriptions/{rid}")
def update_prescription(pid: int, rid: int, body: PrescriptionPatch,
                        s: Session = Depends(get_session)):
    """Изменить назначение. Прежняя версия сохраняется в истории —
    назначение нельзя просто перезаписать (спецификация, п.10)."""
    from ..models import PrescriptionRevision
    p = _presc_owned(s, pid, rid)
    data = body.model_dump(exclude_unset=True)
    reason = (data.pop("reason", "") or "").strip()
    if not data:
        raise HTTPException(400, "Нечего менять")

    s.add(PrescriptionRevision(prescription_id=p.id, doctor_id=current_doctor_id(),
                               reason=reason, snapshot=_snapshot(p)))
    for key, value in data.items():
        setattr(p, key, value)
    if data.get("status") == "cancelled" and not p.cancelled_at:
        p.cancelled_at = clock.now()
    p.updated_at = clock.now()
    s.add(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="prescription",
                     entity_id=p.id, action="update",
                     detail=f"{', '.join(data)}{' | ' + reason if reason else ''}"))
    s.commit(); s.refresh(p)
    return _presc_view(p)


@router.post("/patients/{pid}/prescriptions/{rid}/confirm")
def confirm_prescription(pid: int, rid: int, s: Session = Depends(get_session)):
    """Подтвердить предложение ИИ — только после этого оно становится действующим."""
    p = _presc_owned(s, pid, rid)
    p.confirmed = True
    if p.status == "planned":
        p.status = "active"
    p.updated_at = clock.now()
    s.add(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="prescription",
                     entity_id=p.id, action="confirm", detail=p.drug_name))
    s.commit(); s.refresh(p)
    return _presc_view(p)


@router.get("/patients/{pid}/prescriptions/{rid}/history")
def prescription_history(pid: int, rid: int, s: Session = Depends(get_session)):
    """История изменений назначения — что и когда меняли, с причиной."""
    import json
    from ..models import PrescriptionRevision
    _presc_owned(s, pid, rid)
    rows = s.exec(select(PrescriptionRevision)
                  .where(PrescriptionRevision.prescription_id == rid)
                  .order_by(PrescriptionRevision.changed_at.desc())).all()
    out = []
    for r in rows:
        try:
            prev = json.loads(r.snapshot or "{}")
        except Exception:
            prev = {}
        out.append({"id": r.id, "changed_at": r.changed_at.isoformat(),
                    "reason": r.reason, "previous": prev})
    return {"items": out}


def _presc_view(p: Prescription) -> dict:
    return {
        "id": p.id, "patient_id": p.patient_id, "drug_name": p.drug_name,
        "dose": p.dose, "regimen": p.regimen, "category": p.category,
        "indication": p.indication, "instruction": p.instruction, "route": p.route,
        "frequency": p.frequency, "duration": p.duration,
        "starts_on": p.starts_on.isoformat() if p.starts_on else None,
        "control": p.control,
        "control_date": p.control_date.isoformat() if p.control_date else None,
        "source": p.source, "confirmed": p.confirmed, "priority": p.priority,
        "status": p.status, "cancel_reason": p.cancel_reason, "effect": p.effect,
        "conflict_flag": p.conflict_flag,
        "created_at": p.created_at.isoformat(),
    }


@router.post("/patients/{pid}/prescriptions/dictate")
async def dictate_prescriptions(pid: int, audio: UploadFile = File(None),
                                audio_format: str = Form(""), text: str = Form(""),
                                s: Session = Depends(get_session)):
    """Продиктовать несколько назначений одной фразой → ПРЕДПРОСМОТР.

    По спецификации (п.21) система показывает результат разбора и просит
    подтверждение; ничего не сохраняется молча. Сохранение — обычным
    созданием назначений с source=ai_suggested, которые врач подтверждает.
    """
    get_owned_patient(s, pid)
    require_consent(s, pid)

    said = (text or "").strip()
    if not said and audio is not None:
        from ..services.stt import transcribe
        from ..services.usage import meter
        meter(s, current_doctor_id(), "stt", detail="prescriptions")
        said = transcribe(await audio.read(), audio_format)
    if not said:
        raise HTTPException(400, "Нечего разбирать: пустая диктовка")

    from ..services.rx_dictation import parse
    out = parse(said)
    log_event(s, "prescriptions.dictated",
              {"source": out["source"], "items": len(out["items"])}, current_doctor_id())
    return out
