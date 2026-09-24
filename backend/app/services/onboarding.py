"""Онбординг: учебная песочница и прогресс подсказок.

Принципы (по ТЗ §31 и договорённостям):
- Обучение идёт на ВЫМЫШЛЕННОМ пациенте (is_training=True). Учебные данные НЕ
  попадают в рабочую базу: помеченный пациент исключён из всех рабочих списков
  (см. фильтры is_training==False в роутерах/сервисах), плюс удаляется по
  завершении/пропуску, плюс страховочная зачистка сносит «зависшие» учебные
  записи старше суток (на случай прерванной сессии).
- Прогресс (пройден онбординг, увидена подсказка) — строки DoctorProgress по ключу.
"""
from datetime import timedelta
from sqlmodel import Session, select
from .. import clock
from ..models import (Doctor, DoctorProgress, Patient, Observation, Note, Prescription,
                      SafetyItem, VisitProtocol, Appointment, SourceDocument, PatientConsent,
                      Reminder, Encounter, SickLeave, PatientDiagnosis, PatientExternalId)
from .identity import name_index_for

ONBOARDING_DONE = "onboarding:done"
TRAINING_MAX_AGE_HOURS = 24            # старше — под страховочную зачистку

# Разрешённые ключи точечных подсказок (белый список — чужие ключи не пишем).
TIP_KEYS = {
    "tip:attention",     # блок «Требуют внимания» = автосписок (C01–C05)
    "tip:protocol",      # селектор шаблонов T01–T12
    "tip:integrity",     # блок «Проверка карты» (D/Q/I)
    "tip:timezone",      # тихие часы/дайджест — в таймзоне врача
    "tip:dictation",     # называть нового пациента в смешанной диктовке
    "tip:identity",      # выбор нужного тёзки
    "tip:help",          # памятка в «Помощи»
}


# ── Прогресс ────────────────────────────────────────────────────────────────
def _has(s: Session, doctor_id: int, key: str) -> bool:
    return s.exec(select(DoctorProgress).where(
        DoctorProgress.doctor_id == doctor_id, DoctorProgress.key == key)).first() is not None


def mark_seen(s: Session, doctor_id: int, key: str) -> None:
    """Идемпотентно отметить ключ увиденным (повторный вызов ничего не дублирует)."""
    if not _has(s, doctor_id, key):
        s.add(DoctorProgress(doctor_id=doctor_id, key=key))
        s.commit()


def progress(s: Session, doctor_id: int) -> dict:
    keys = {r.key for r in s.exec(select(DoctorProgress).where(
        DoctorProgress.doctor_id == doctor_id)).all()}
    return {
        "onboarding_done": ONBOARDING_DONE in keys,
        "tips_seen": sorted(k for k in keys if k.startswith("tip:")),
    }


# ── Учебная песочница ────────────────────────────────────────────────────────
def _delete_training_patient(s: Session, p: Patient) -> None:
    """Снести учебного пациента и ВСЁ связанное — под ноль, без сирот."""
    pid = p.id
    for model in (Observation, Note, Prescription, SafetyItem, VisitProtocol,
                  Appointment, SourceDocument, PatientConsent, Encounter, SickLeave,
                  PatientDiagnosis, PatientExternalId):
        for r in s.exec(select(model).where(model.patient_id == pid)).all():
            s.delete(r)
    for r in s.exec(select(Reminder).where(Reminder.patient_id == pid)).all():
        s.delete(r)            # учебные задачи удаляем целиком (в отличие от рабочего erase)
    s.delete(p)
    s.commit()


def start_sandbox(s: Session, doctor_id: int) -> Patient:
    """Создать (или вернуть уже существующего) учебного пациента для онбординга.

    Идемпотентно: если незавершённая учебная сессия уже есть — возвращаем её,
    не плодим дубли.
    """
    existing = s.exec(select(Patient).where(
        Patient.doctor_id == doctor_id, Patient.is_training == True)).first()
    if existing:
        return existing
    p = Patient(
        doctor_id=doctor_id, is_training=True,
        last_name="Демонстрационный", first_name="Пациент", middle_name="Учебный",
        sex="м", diagnosis_code="", diagnosis_text="Учебная карта для обучения",
        name_index=name_index_for("Демонстрационный", "Пациент"),
    )
    s.add(p); s.commit(); s.refresh(p)
    return p


def finish_sandbox(s: Session, doctor_id: int, mark_done: bool = True) -> None:
    """Завершение/пропуск онбординга: удалить учебного пациента; при mark_done —
    пометить онбординг пройденным (при пропуске тоже помечаем, чтобы не показывать снова)."""
    for p in s.exec(select(Patient).where(
            Patient.doctor_id == doctor_id, Patient.is_training == True)).all():
        _delete_training_patient(s, p)
    if mark_done:
        mark_seen(s, doctor_id, ONBOARDING_DONE)


def sweep_stale_training(s: Session) -> int:
    """Страховочная зачистка: удалить учебных пациентов старше суток у всех врачей
    (на случай прерванной сессии, когда finish_sandbox не был вызван). Возвращает
    число удалённых. Идемпотентно, безопасно запускать хоть каждый час."""
    cutoff = clock.now() - timedelta(hours=TRAINING_MAX_AGE_HOURS)
    stale = s.exec(select(Patient).where(
        Patient.is_training == True, Patient.created_at < cutoff)).all()
    n = len(stale)
    for p in stale:
        _delete_training_patient(s, p)
    return n
