"""Демо-данные для разработки: один врач и несколько пациентов с историей."""
from datetime import date, datetime, timedelta
from sqlmodel import Session, select
from .db import engine, init_db
from . import clock
from .security import hash_password
from .models import (Doctor, Patient, Observation, SafetyItem, Reminder, Appointment,
                     PatientDiagnosis, PatientConsent, UsageRecord)


def run():
    init_db()
    with Session(engine) as s:
        if s.exec(select(Doctor)).first():
            print("Данные уже есть — пропускаю seed.")
            return

        doc = Doctor(full_name="Смирнов Андрей Викторович", specialty="Уролог",
                     license_no="77-01-002345", email="doctor@demo.ru", phone="+70000000000",
                     password_hash=hash_password("demo12345"), role="doctor", is_demo=True)
        s.add(doc); s.commit(); s.refresh(doc)

        p1 = Patient(doctor_id=doc.id, last_name="Иванов", first_name="Пётр",
                     middle_name="Сергеевич", birth_date=date(1961, 8, 3), sex="м",
                     phone="+7 900 000-00-01", diagnosis_code="N40.0",
                     diagnosis_text="ДГПЖ, наблюдение")
        p2 = Patient(doctor_id=doc.id, last_name="Кузнецов", first_name="Александр",
                     middle_name="Ильич", birth_date=date(1954, 2, 14), sex="м",
                     diagnosis_code="N40.0", diagnosis_text="ДГПЖ")
        p3 = Patient(doctor_id=doc.id, last_name="Сергеева", first_name="Ольга",
                     middle_name="Викторовна", birth_date=date(1970, 6, 1), sex="ж",
                     diagnosis_code="N30.0", diagnosis_text="Цистит")
        for p in (p1, p2, p3):
            s.add(p)
        s.commit(); [s.refresh(p) for p in (p1, p2, p3)]
        from .services.identity import name_index_for
        for p in (p1, p2, p3):
            p.name_index = name_index_for(p.last_name, p.first_name); s.add(p)
        s.commit()

        T = clock.today()
        # демо-расход ИИ за последние дни (для аналитики админки)
        import random as _r
        for dd in range(0, 10):
            day = clock.now() - timedelta(days=dd)
            for kind, base in (("ocr", 12), ("stt", 6), ("llm", 20)):
                for _ in range(_r.randint(base // 2, base)):
                    s.add(UsageRecord(doctor_id=doc.id, kind=kind, units=1, created_at=day))
        # демо-события использования (обезличенно) для графиков и списка
        from .models import AnalyticsEvent
        evs = ["patient.opened", "note.added", "prescription.created", "document.uploaded",
               "appointment.created", "reminder.created", "protocol.saved", "search.used"]
        for dd in range(0, 14):
            day = clock.now() - timedelta(days=dd)
            for _ in range(_r.randint(3, 10)):
                s.add(AnalyticsEvent(doctor_id=doc.id, event=_r.choice(evs), created_at=day))
                # диагнозы как записи (основной) — согласованы с шапкой карточки
        for p in (p1, p2, p3):
            s.add(PatientConsent(patient_id=p.id, method="electronic", status="granted",
                                 verified=True, signer_name=f"{p.last_name} {p.first_name}",
                                 verify_note="демо: электронное согласие"))
            if p.diagnosis_code:
                s.add(PatientDiagnosis(patient_id=p.id, code=p.diagnosis_code,
                                       title=p.diagnosis_text, wording=p.diagnosis_text,
                                       is_primary=True, status="active"))
        # история PSA — даты относительно настоящего «сегодня», последняя ~3 дня назад
        psa = [(T - timedelta(days=600), 1.0), (T - timedelta(days=450), 1.8),
               (T - timedelta(days=300), 2.1), (T - timedelta(days=180), 2.4),
               (T - timedelta(days=90), 3.1), (T - timedelta(days=3), 4.82)]
        for d, v in psa:
            s.add(Observation(patient_id=p1.id, parameter_code="psa_total",
                              value_num=v, unit="нг/мл", effective_date=d, status="confirmed"))
        for d, v in [(T - timedelta(days=180), 54), (T - timedelta(days=3), 68)]:
            s.add(Observation(patient_id=p1.id, parameter_code="prostate_volume",
                              value_num=v, unit="см³", effective_date=d, status="confirmed"))
        s.add(Observation(patient_id=p2.id, parameter_code="psa_total",
                          value_num=6.1, unit="нг/мл", effective_date=T - timedelta(days=4),
                          status="confirmed"))

        # аллергия у p3 — для демонстрации конфликта назначения
        s.add(SafetyItem(patient_id=p3.id, kind="allergy", state="present",
                         detail="Фторхинолоны — отёк Квинке, 2021"))

        s.add(Reminder(doctor_id=doc.id, patient_id=p2.id,
                       title="Контроль PSA — Кузнецов А. И.", kind="control",
                       project="Контроли", priority=2, repeat_days=90,
                       due_at=clock.now() - timedelta(days=4)))
        s.add(Reminder(doctor_id=doc.id, patient_id=p1.id,
                       title="Снять катетер — Петрова М. Н.", kind="task",
                       project="Контроли", priority=1, due_at=clock.now()))
        s.add(Reminder(doctor_id=doc.id, title="Заказать расходники для приёма",
                       kind="task", project="Работа", priority=3,
                       due_at=clock.now() + timedelta(days=2)))
        s.add(Reminder(doctor_id=doc.id, title="Позвонить в лабораторию по договору",
                       kind="call", project="Работа", labels="звонок",
                       due_at=clock.now() + timedelta(days=1)))

        # приёмы с временем — относительно сегодня (для календаря месяц/неделя/день)
        def at(days, h, m):
            return datetime.combine(T + timedelta(days=days), datetime.min.time()).replace(hour=h, minute=m)
        appts = [
            (p1.id, at(0, 9, 30), "repeat", "ДГПЖ, наблюдение"),
            (p3.id, at(0, 10, 15), "primary", "первичный приём"),
            (p2.id, at(0, 11, 0), "repeat", "контроль PSA"),
            (p1.id, at(2, 12, 30), "repeat", "повторный"),
            (p2.id, at(6, 9, 0), "repeat", "ДГПЖ"),
            (p3.id, at(6, 15, 30), "repeat", "контроль"),
        ]
        for pid, dt, kind, reason in appts:
            s.add(Appointment(doctor_id=doc.id, patient_id=pid, starts_at=dt,
                              kind=kind, reason=reason))
        s.commit()
        print("Seed выполнен: 1 врач, 3 пациента, история PSA, приёмы, напоминания.")


if __name__ == "__main__":
    run()
