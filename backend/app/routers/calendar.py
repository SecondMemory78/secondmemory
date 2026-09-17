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


@router.get("/export.ics")
def export_ics(s: Session = Depends(get_session)):
    """Выгрузка приёмов в стандартный .ics — врач сам добавит в любой календарь.
    Данные пациентов НЕ уходят в стороннее облако автоматически (152-ФЗ)."""
    since = clock.now() - timedelta(days=30)
    rows = s.exec(select(Appointment).where(
        Appointment.doctor_id == current_doctor_id(),
        Appointment.starts_at >= since)).all()
    rows = [a for a in rows if a.status != "cancelled"]
    rows.sort(key=lambda a: a.starts_at)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Вторая память//RU", "CALSCALE:GREGORIAN"]
    for a in rows:
        p = s.get(Patient, a.patient_id)
        name = f"{p.last_name} {p.first_name[:1]}." if p else "Пациент"
        end = a.starts_at + timedelta(minutes=30)
        lines += ["BEGIN:VEVENT", f"UID:appt-{a.id}@vtoraya-pamyat",
                  f"DTSTAMP:{_ics_dt(clock.now())}", f"DTSTART:{_ics_dt(a.starts_at)}",
                  f"DTEND:{_ics_dt(end)}",
                  f"SUMMARY:Приём: {name}", f"DESCRIPTION:{a.reason or ''}", "END:VEVENT"]
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
    pts = s.exec(select(Patient).where(Patient.doctor_id == current_doctor_id())).all()
    for p in pts:
        if p.last_name.lower() == last.lower():
            return p
    p = Patient(doctor_id=current_doctor_id(), last_name=last,
                first_name=parts[1] if len(parts) > 1 else "",
                middle_name=parts[2] if len(parts) > 2 else "")
    s.add(p); s.commit(); s.refresh(p)
    return p
