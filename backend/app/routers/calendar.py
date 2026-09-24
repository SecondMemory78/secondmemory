"""Импорт приёмов в календарь из CSV.

Формат CSV (заголовок обязателен), разделитель — запятая или точка с запятой:
    date,time,patient,reason,kind
    2026-03-20,09:30,Иванов,контроль PSA,repeat
    2026-03-20,10:00,Сергеева Ольга,первичный,primary

Пациент ищется по фамилии; если не найден — создаётся минимальная карточка.
"""
import csv
from ..deps import current_doctor_id
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session, select
from ..db import get_session
from ..models import Appointment, Patient
from ..services.telemetry import log_event
from .. import clock

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

TEMPLATE = "date,time,patient,reason,kind\n2026-03-20,09:30,Иванов,контроль PSA,repeat\n"


def _ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _ics_escape(text: str) -> str:
    """Экранирование спецсимволов текста для .ics (RFC 5545)."""
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


# Обезличенные заголовки типов приёма/дела — БЕЗ ФИО и диагноза (152-ФЗ, ТЗ).
_APPT_TITLE = {"primary": "Первичный приём", "repeat": "Повторный приём"}
_REM_TITLE = {"control": "Контроль", "appointment": "Приём", "call": "Звонок", "task": "Задача"}


@router.get("/export.ics")
def export_ics(s: Session = Depends(get_session)):
    """Выгрузка приёмов и напоминаний в стандартный .ics.

    ЗАГОЛОВКИ ОБЕЗЛИЧЕНЫ: в событие не попадают ФИО пациента, диагноз или причина —
    только тип дела и время. Файл врач добавляет в свой календарь (часто облачный,
    синхронизируемый), поэтому персональных данных пациента в нём быть не должно
    (152-ФЗ). Идентификация — только по внутренней ссылке (UID), которую видит лишь
    приложение, а сам пациент открывается в «Второй памяти» по этому UID.
    """
    from ..models import Reminder
    did = current_doctor_id()
    now = clock.now()
    since = now - timedelta(days=30)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Вторая память//RU", "CALSCALE:GREGORIAN"]

    appts = s.exec(select(Appointment).where(
        Appointment.doctor_id == did, Appointment.starts_at >= since)).all()
    for a in sorted((x for x in appts if x.status != "cancelled"), key=lambda x: x.starts_at):
        title = _APPT_TITLE.get(a.kind, "Приём")
        end = a.starts_at + timedelta(minutes=30)
        lines += ["BEGIN:VEVENT", f"UID:appt-{a.id}@vtoraya-pamyat",
                  f"DTSTAMP:{_ics_dt(now)}", f"DTSTART:{_ics_dt(a.starts_at)}",
                  f"DTEND:{_ics_dt(end)}",
                  f"SUMMARY:{_ics_escape(title)}",
                  "DESCRIPTION:Откройте в приложении «Вторая память»", "END:VEVENT"]

    rems = s.exec(select(Reminder).where(
        Reminder.doctor_id == did, Reminder.due_at != None,
        Reminder.due_at >= since, Reminder.status == "open")).all()
    for r in sorted(rems, key=lambda x: x.due_at):
        title = _REM_TITLE.get(r.kind, "Дело")
        end = r.due_at + timedelta(minutes=15)
        lines += ["BEGIN:VEVENT", f"UID:rem-{r.id}@vtoraya-pamyat",
                  f"DTSTAMP:{_ics_dt(now)}", f"DTSTART:{_ics_dt(r.due_at)}",
                  f"DTEND:{_ics_dt(end)}",
                  f"SUMMARY:{_ics_escape(title)}",
                  "DESCRIPTION:Откройте в приложении «Вторая память»", "END:VEVENT"]

    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines)
    return Response(content=ics, media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=second-memory.ics"})


@router.get("/import/template", response_class=PlainTextResponse)
def template():
    return TEMPLATE


@router.post("/import")
async def import_csv(file: UploadFile = File(...), s: Session = Depends(get_session)):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    dialect = ";" if raw.count(";") > raw.count(",") else ","
    reader = csv.DictReader(io.StringIO(raw), delimiter=dialect)

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            d = (row.get("date") or "").strip()
            t = (row.get("time") or "09:00").strip()
            name = (row.get("patient") or "").strip()
            if not d or not name:
                skipped += 1
                continue
            starts = datetime.fromisoformat(f"{d}T{t}:00" if len(t) == 5 else f"{d}T{t}")
            patient = _match_or_create(name, s)
            a = Appointment(doctor_id=current_doctor_id(), patient_id=patient.id, starts_at=starts,
                            kind=(row.get("kind") or "repeat").strip(),
                            reason=(row.get("reason") or "").strip())
            s.add(a); created += 1
        except Exception as e:
            errors.append(f"строка {i}: {e}")
    s.commit()
    log_event(s, "calendar.import", {"created": created, "skipped": skipped})
    return {"created": created, "skipped": skipped, "errors": errors}


def _match_or_create(name: str, s: Session) -> Patient:
    parts = name.split()
    last = parts[0]
    pts = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id(), Patient.is_training == False)).all()
    for p in pts:
        if p.last_name.lower() == last.lower():
            return p
    p = Patient(doctor_id=current_doctor_id(), last_name=last,
                first_name=parts[1] if len(parts) > 1 else "",
                middle_name=parts[2] if len(parts) > 2 else "")
    s.add(p); s.commit(); s.refresh(p)
    return p
