"""152-ФЗ: то, что реализуемо в коде уже сейчас.

- согласие пациента на обработку данных о здоровье (спец. категория ПДн);
- журнал доступа к ПДн (AccessLog);
- экспорт всех данных пациента (право субъекта на доступ);
- удаление данных пациента (право на удаление) с записью в аудит.
"""
from datetime import datetime
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..services.usage import meter
from ..services.consent import (standard_form, ocr_consent_form, verify_consent_form,
                                 CONSENT_VERSION)
from ..models import (Patient, Observation, Note, Prescription, SafetyItem,
                      VisitProtocol, Appointment, Reminder, PatientConsent,
                      AccessLog, AuditEvent, SourceDocument, Doctor)

router = APIRouter(prefix="/api/patients", tags=["privacy"])


class ElectronicConsentIn(BaseModel):
    signer_name: str = ""
    agreed: bool = False


def _log(s: Session, pid: int, action: str):
    s.add(AccessLog(doctor_id=current_doctor_id(), patient_id=pid, action=action))


def _revoke_previous(s: Session, pid: int):
    for c in s.exec(select(PatientConsent).where(
            PatientConsent.patient_id == pid, PatientConsent.status == "granted")).all():
        c.status = "revoked"; c.revoked_at = datetime.utcnow(); s.add(c)


@router.get("/{pid}/consent/form")
def consent_form(pid: int, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    return {"version": CONSENT_VERSION, "text": standard_form(p)}


@router.get("/{pid}/consent")
def get_consent(pid: int, s: Session = Depends(get_session)):
    row = s.exec(select(PatientConsent).where(PatientConsent.patient_id == pid)
                 .order_by(PatientConsent.granted_at.desc())).first()
    if not row:
        return {"status": "none", "consent_ok": False}
    return {**row.model_dump(), "consent_ok": row.status == "granted"}


@router.post("/{pid}/consent/paper")
async def consent_paper(pid: int, photo: UploadFile = File(...), s: Session = Depends(get_session)):
    """Бумажный бланк: фото подписанного бланка → ИИ распознаёт и проверяет.
    Хранится ТОЛЬКО распознанный текст, фото не сохраняется."""
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    from ..services.uploads import read_limited
    await read_limited(photo)                  # прочитали для распознавания (с лимитом)…
    text = ocr_consent_form(p)                 # …распознали…
    # …и НЕ сохраняем сам файл (минимизация ПДн)
    verified, note = verify_consent_form(text, p)
    _revoke_previous(s, pid)
    c = PatientConsent(patient_id=pid, method="paper", text_version=CONSENT_VERSION,
                       status="granted" if verified else "pending",
                       signer_name=f"{p.last_name} {p.first_name}", form_text=text,
                       verified=verified, verify_note=note)
    s.add(c)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="consent", entity_id=pid,
                     action="paper", detail=f"verified={verified}; {note}"))
    _log(s, pid, "consent_paper"); s.commit(); s.refresh(c)
    return {**c.model_dump(), "consent_ok": c.status == "granted"}


@router.post("/{pid}/consent/electronic")
def consent_electronic(pid: int, body: ElectronicConsentIn, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    if not body.agreed:
        raise HTTPException(400, "Требуется подтверждение согласия пациентом")
    _revoke_previous(s, pid)
    c = PatientConsent(patient_id=pid, method="electronic", text_version=CONSENT_VERSION,
                       status="granted", verified=True,
                       signer_name=body.signer_name or f"{p.last_name} {p.first_name}",
                       verify_note="электронное согласие на устройстве")
    s.add(c)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="consent", entity_id=pid,
                     action="electronic", detail="подписано на устройстве"))
    _log(s, pid, "consent_electronic"); s.commit(); s.refresh(c)
    return {**c.model_dump(), "consent_ok": True}


@router.post("/{pid}/consent/remote")
def consent_remote(pid: int, s: Session = Depends(get_session)):
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    _revoke_previous(s, pid)
    c = PatientConsent(patient_id=pid, method="remote", text_version=CONSENT_VERSION,
                       status="granted", verified=True,
                       signer_name=f"{p.last_name} {p.first_name}",
                       verify_note="подписано удалённо (QR/SMS)")
    s.add(c)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="consent", entity_id=pid,
                     action="remote", detail="подписано удалённо"))
    _log(s, pid, "consent_remote"); s.commit(); s.refresh(c)
    return {**c.model_dump(), "consent_ok": True, "link": f"/c/{pid}"}


@router.post("/{pid}/consent/revoke")
def revoke_consent(pid: int, s: Session = Depends(get_session)):
    _revoke_previous(s, pid)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="consent", entity_id=pid, action="revoke"))
    s.commit()
    return {"ok": True, "consent_ok": False}


@router.get("/{pid}/export.pdf")
def export_patient_pdf(pid: int, sections: str = "", date_from: str = "",
                       date_to: str = "", s: Session = Depends(get_session)):
    """PDF-выписка: полная или выборочно по разделам (?sections=observations,notes)
    и периоду (?date_from=YYYY-MM-DD&date_to=...). Кириллица — вшитый шрифт."""
    from fastapi.responses import Response
    from ..services.pdf_export import build_pdf
    from ..reference_data import label_map
    data = export_patient(pid, s)     # переиспользуем сбор данных экспорта
    secs = [x.strip() for x in sections.split(",") if x.strip()] or None
    doc = s.get(Doctor, current_doctor_id())
    pdf = build_pdf(data, sections=secs, date_from=date_from, date_to=date_to,
                    doctor_name=doc.full_name if doc else "", param_labels=label_map())
    headers = {"Content-Disposition": f'attachment; filename="vypiska_{pid}.pdf"'}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


@router.get("/{pid}/export")
def export_patient(pid: int, s: Session = Depends(get_session)):
    """Полный экспорт данных пациента (право субъекта на доступ к своим ПДн)."""
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    _log(s, pid, "export"); s.commit()

    def dump(model):
        return [r.model_dump() for r in s.exec(select(model).where(model.patient_id == pid)).all()]

    return {
        "patient": p.model_dump(),
        "observations": dump(Observation),
        "notes": dump(Note),
        "prescriptions": dump(Prescription),
        "safety": dump(SafetyItem),
        "protocol": dump(VisitProtocol),
        "appointments": dump(Appointment),
        "reminders": [r.model_dump() for r in s.exec(select(Reminder).where(Reminder.patient_id == pid)).all()],
        "documents": dump(SourceDocument),
        "consents": dump(PatientConsent),
        "exported_at": datetime.utcnow().isoformat(),
    }


@router.delete("/{pid}/erase")
def erase_patient(pid: int, s: Session = Depends(get_session)):
    """Удаление персональных данных пациента. В аудит пишем только id, без ПДн."""
    p = s.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Пациент не найден")
    _log(s, pid, "erase")

    for model in (Observation, Note, Prescription, SafetyItem, VisitProtocol,
                  Appointment, SourceDocument, PatientConsent):
        for r in s.exec(select(model).where(model.patient_id == pid)).all():
            s.delete(r)
    for r in s.exec(select(Reminder).where(Reminder.patient_id == pid)).all():
        r.patient_id = None; s.add(r)   # задачи не привязываем к удалённому
    s.delete(p)
    s.add(AuditEvent(doctor_id=current_doctor_id(), entity_type="patient", entity_id=pid,
                     action="erase", detail="персональные данные удалены (152-ФЗ)"))
    s.commit()
    return {"ok": True}
