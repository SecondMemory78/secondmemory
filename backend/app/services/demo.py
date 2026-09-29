"""Одноразовые демо-сессии.

Раньше кнопка «Посмотреть демо» пускала ВСЕХ в один общий демо-аккаунт: любой
посетитель менял данные, которые потом видели следующие. Теперь каждый заход
создаёт СВОЕГО демо-врача со своей копией демо-данных, а через DEMO_TTL старые
удаляются целиком. Демо — витрина: посмотреть и потыкать, ничего не копится.
"""
from datetime import timedelta
from sqlmodel import Session, select
from .. import clock
from ..models import (Doctor, Patient, Observation, SafetyItem, Reminder, Appointment,
                      PatientDiagnosis, PatientConsent, UsageRecord, Note, Device,
                      AuthSession, Notification, AnalyticsEvent, AuditEvent, AccessLog,
                      VisitProtocol, VisitSession, Encounter, Prescription, Trigger,
                      DoctorNote, AssistantAction, Subscription, SupportThread,
                      SupportMessage, SourceDocument, DoctorProgress,
                      PushSubscription, PushDelivery, ReminderAlert)

DEMO_TTL = timedelta(hours=1)          # сколько живёт демо-аккаунт
DEMO_EMAIL_PREFIX = "demo+"            # по нему узнаём одноразовые демо-аккаунты


def is_disposable_demo(doc: Doctor) -> bool:
    return bool(doc and doc.is_demo and (doc.email or "").startswith(DEMO_EMAIL_PREFIX))


def create_demo_doctor(s: Session) -> Doctor:
    """Новый изолированный демо-врач со своей копией демо-данных."""
    from ..seed import populate_for
    from ..security import hash_password
    stamp = int(clock.now().timestamp() * 1000)
    doc = Doctor(full_name="Демо-врач", specialty="Уролог",
                 email=f"{DEMO_EMAIL_PREFIX}{stamp}@demo.local",
                 phone="", password_hash=hash_password(f"demo-{stamp}"),
                 role="doctor", is_demo=True)
    s.add(doc); s.commit(); s.refresh(doc)
    populate_for(s, doc)
    return doc


# Таблицы, которые чистим при удалении демо-врача. Порядок важен: сначала то,
# что ссылается на пациента/приём, потом сами пациенты, потом врач.
_PATIENT_SCOPED = [Observation, SafetyItem, PatientDiagnosis, PatientConsent,
                   Note, Device, VisitProtocol, Prescription, SourceDocument]
_DOCTOR_SCOPED = [Reminder, Appointment, UsageRecord, AuthSession, Notification,
                  AnalyticsEvent, AuditEvent, AccessLog, VisitSession, Encounter,
                  Trigger, DoctorNote, AssistantAction, Subscription,
                  SupportThread, SupportMessage, DoctorProgress,
                  PushSubscription, PushDelivery, ReminderAlert]


def purge_demo_doctor(s: Session, doc: Doctor) -> None:
    """Полностью удаляет демо-врача и все его данные."""
    pids = [p.id for p in s.exec(select(Patient).where(Patient.doctor_id == doc.id)).all()]
    for model in _PATIENT_SCOPED:
        if not pids:
            break
        if not hasattr(model, "patient_id"):
            continue
        for row in s.exec(select(model).where(model.patient_id.in_(pids))).all():
            s.delete(row)
    for model in _DOCTOR_SCOPED:
        if not hasattr(model, "doctor_id"):
            continue
        for row in s.exec(select(model).where(model.doctor_id == doc.id)).all():
            s.delete(row)
    for p in s.exec(select(Patient).where(Patient.doctor_id == doc.id)).all():
        s.delete(p)
    s.delete(doc)
    s.commit()


def purge_expired_demos(s: Session) -> int:
    """Удаляет демо-аккаунты старше DEMO_TTL. Возвращает число удалённых.

    Демо с ЖИВОЙ сессией не трогаем, даже если формально просрочен: иначе
    можно выбить из приложения человека, который прямо сейчас смотрит демо
    (а в тестах — сбить сдвинутыми часами чужой аккаунт)."""
    cutoff = clock.now() - DEMO_TTL
    stale = [d for d in s.exec(select(Doctor).where(Doctor.is_demo == True)).all()   # noqa: E712
             if is_disposable_demo(d) and d.created_at < cutoff]
    removed = 0
    for d in stale:
        alive = s.exec(select(AuthSession).where(
            AuthSession.doctor_id == d.id, AuthSession.expires_at > clock.now())).first()
        if alive:
            continue
        purge_demo_doctor(s, d)
        removed += 1
    return removed
