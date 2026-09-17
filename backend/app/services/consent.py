"""Согласие 152-ФЗ: стандартный бланк, распознавание и проверка (ИИ), барьер.

Инварианты:
- без активного granted-согласия приём вести нельзя (consent_ok → False);
- из фото бланка храним ТОЛЬКО распознанный текст, само фото не сохраняем;
- ИИ проверяет, что бланк наш, заполнен на этого пациента и подписан.
В dev распознавание/проверка — детерминированная заглушка; в проде — Yandex Vision.
"""
from sqlmodel import Session, select
from ..models import PatientConsent, Patient

CONSENT_VERSION = "v1-2026"

STANDARD_FORM = (
    "СОГЛАСИЕ на обработку персональных данных, в том числе специальной категории "
    "(сведения о состоянии здоровья), в соответствии с Федеральным законом № 152-ФЗ "
    "«О персональных данных». Пациент: {fio}. Дата рождения: {dob}. "
    "Настоящим я даю согласие оператору на обработку моих персональных данных "
    "и данных о состоянии здоровья в целях оказания медицинской помощи и ведения "
    "медицинской документации. Согласие может быть отозвано письменным заявлением. "
    "Подпись пациента: ____________   Дата: __________"
)


def standard_form(patient: Patient) -> str:
    fio = f"{patient.last_name} {patient.first_name} {patient.middle_name or ''}".strip()
    dob = patient.birth_date.isoformat() if patient.birth_date else "__.__.____"
    return STANDARD_FORM.format(fio=fio, dob=dob)


def ocr_consent_form(patient: Patient, provider: str = "stub") -> str:
    """Распознать текст с фото подписанного бланка.
    dev-заглушка возвращает наш бланк с ФИО пациента и отметкой подписи."""
    text = standard_form(patient)
    return text.replace("Подпись пациента: ____________", "Подпись пациента: /подпись/")


def verify_consent_form(text: str, patient: Patient) -> tuple[bool, str]:
    """ИИ-проверка бланка: наш ли это бланк, на того ли пациента, есть ли подпись."""
    low = (text or "").lower()
    checks = []
    is_our = "152-фз" in low or "персональных данных" in low
    checks.append(("бланк по 152-ФЗ", is_our))
    name_ok = patient.last_name.lower() in low
    checks.append(("ФИО пациента совпадает", name_ok))
    signed = "подпис" in low
    checks.append(("есть подпись", signed))
    ok = is_our and name_ok and signed
    note = "; ".join(f"{'✓' if v else '✗'} {n}" for n, v in checks)
    return ok, note


def active_consent(s: Session, patient_id: int):
    return s.exec(select(PatientConsent).where(
        PatientConsent.patient_id == patient_id,
        PatientConsent.status == "granted")).first()


def consent_ok(s: Session, patient_id: int) -> bool:
    return active_consent(s, patient_id) is not None


def require_consent(s: Session, patient_id: int):
    """Барьер: без согласия нельзя вносить НИЧЕГО в карту пациента."""
    from fastapi import HTTPException
    if not consent_ok(s, patient_id):
        raise HTTPException(403, "Нет согласия на обработку ПДн — заполнять карту пациента нельзя. Оформите согласие.")
