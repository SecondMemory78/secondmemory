"""Приём: длительность, завершение врачом, «не пришёл», предупреждение о накладках."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
seed.run()
c = TestClient(app)


def _pid():
    return c.post("/api/patients", json={"last_name": "Приёмов", "first_name": "Тест"}).json()["id"]


def _appt(starts_at, duration_min=20):
    return c.post("/api/appointments", json={"patient_id": _pid(), "starts_at": starts_at,
                                             "kind": "repeat", "reason": "контроль",
                                             "duration_min": duration_min}).json()


def test_duration_defaults_and_end_time():
    a = _appt("2026-08-10T10:00:00")
    assert a["duration_min"] == 20 and a["ends_time"] == "10:20"
    b = _appt("2026-08-11T10:00:00", 45)
    assert b["duration_min"] == 45 and b["ends_time"] == "10:45"


def test_duration_is_clamped():
    a = _appt("2026-08-12T10:00:00", 1)          # слишком мало
    assert a["duration_min"] == 5
    b = _appt("2026-08-13T10:00:00", 10000)      # слишком много
    assert b["duration_min"] == 480


def test_doctor_finishes_appointment():
    a = _appt("2026-08-14T10:00:00")
    assert a["status"] == "planned" and a["ended_at"] is None
    r = c.post(f"/api/appointments/{a['id']}/status", json={"status": "done"}).json()
    assert r["status"] == "done" and r["ended_at"]        # время ставится по нажатию врача


def test_no_show_and_back_to_planned():
    a = _appt("2026-08-15T10:00:00")
    r = c.post(f"/api/appointments/{a['id']}/status", json={"status": "no_show"}).json()
    assert r["status"] == "no_show" and r["ended_at"] is None
    back = c.post(f"/api/appointments/{a['id']}/status", json={"status": "planned"}).json()
    assert back["status"] == "planned"


def test_bad_status_rejected_and_foreign_404():
    a = _appt("2026-08-16T10:00:00")
    assert c.post(f"/api/appointments/{a['id']}/status", json={"status": "нечто"}).status_code == 400
    assert c.post("/api/appointments/999999/status", json={"status": "done"}).status_code == 404


def test_conflicts_warn_but_do_not_block():
    a = _appt("2026-08-17T10:00:00", 30)         # 10:00–10:30
    r = c.get("/api/appointments/conflicts",
              params={"starts_at": "2026-08-17T10:15:00", "duration_min": 20}).json()
    assert r["has_conflict"] and r["items"][0]["id"] == a["id"]
    # и всё равно можно создать — это подсказка, не запрет
    b = _appt("2026-08-17T10:15:00", 20)
    assert b["id"]


def test_no_conflict_when_times_do_not_overlap():
    _appt("2026-08-18T10:00:00", 20)             # 10:00–10:20
    r = c.get("/api/appointments/conflicts",
              params={"starts_at": "2026-08-18T10:20:00", "duration_min": 20}).json()
    assert r["has_conflict"] is False            # встык — не наложение


def test_cancelled_appointment_is_not_a_conflict():
    a = _appt("2026-08-19T10:00:00", 30)
    c.post(f"/api/appointments/{a['id']}/cancel")
    r = c.get("/api/appointments/conflicts",
              params={"starts_at": "2026-08-19T10:10:00", "duration_min": 20}).json()
    assert r["has_conflict"] is False


# ── перенос приёма: сохраняем историю ────────────────────────────────────────
def test_reschedule_records_original_time_and_count():
    a = _appt("2026-08-20T10:00:00")
    assert a["rescheduled_from"] is None and a["reschedule_count"] == 0
    r1 = c.patch(f"/api/appointments/{a['id']}", json={"starts_at": "2026-08-21T11:00:00"}).json()
    assert r1["rescheduled_from"].startswith("2026-08-20T10:00")   # первое исходное время
    assert r1["reschedule_count"] == 1 and r1["time"] == "11:00"
    r2 = c.patch(f"/api/appointments/{a['id']}", json={"starts_at": "2026-08-22T12:00:00"}).json()
    assert r2["rescheduled_from"].startswith("2026-08-20T10:00")   # оно НЕ перезаписывается
    assert r2["reschedule_count"] == 2


def test_editing_without_time_change_is_not_a_reschedule():
    a = _appt("2026-08-23T10:00:00")
    r = c.patch(f"/api/appointments/{a['id']}", json={"reason": "другая причина"}).json()
    assert r["reschedule_count"] == 0 and r["rescheduled_from"] is None
    same = c.patch(f"/api/appointments/{a['id']}", json={"starts_at": "2026-08-23T10:00:00"}).json()
    assert same["reschedule_count"] == 0                            # то же время — не перенос


def test_reschedule_is_written_to_audit():
    from app.db import engine
    from app.models import AuditEvent
    from sqlmodel import Session, select
    a = _appt("2026-08-24T10:00:00")
    c.patch(f"/api/appointments/{a['id']}", json={"starts_at": "2026-08-25T09:00:00"})
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(AuditEvent.entity_type == "appointment",
                                             AuditEvent.entity_id == a["id"],
                                             AuditEvent.action == "reschedule")).all()
    assert ev and "→" in ev[-1].detail


# ── «Требуют внимания»: согласие как блокирующий пункт ───────────────────────
def test_attention_flags_patient_without_consent():
    pid = c.post("/api/patients", json={"last_name": "Несогласный", "first_name": "Т"}).json()["id"]
    attn = c.get("/api/dashboard/attention").json()
    item = [i for i in attn["items"] if i["patient_id"] == pid]
    assert item and any(r["type"] == "no_consent" for r in item[0]["reasons"])


def test_attention_drops_consent_flag_once_granted():
    pid = c.post("/api/patients", json={"last_name": "Согласный", "first_name": "Т"}).json()["id"]
    c.post(f"/api/patients/{pid}/consent/electronic", json={"agreed": True})
    attn = c.get("/api/dashboard/attention").json()
    item = [i for i in attn["items"] if i["patient_id"] == pid]
    assert not item or not any(r["type"] == "no_consent" for r in item[0]["reasons"])


# ── печать расписания дня/недели ─────────────────────────────────────────────
def test_schedule_pdf_for_a_day():
    pid = _pid()
    c.post("/api/appointments", json={"patient_id": pid, "starts_at": "2026-09-01T09:00:00",
                                      "kind": "primary", "reason": "первичный осмотр"})
    c.post("/api/reminders", json={"title": "позвонить в лабораторию",
                                   "due_at": "2026-09-01T12:00:00", "kind": "task"})
    r = c.get("/api/appointments/schedule.pdf",
              params={"date_from": "2026-09-01", "date_to": "2026-09-01"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF" and len(r.content) > 1000


def test_schedule_pdf_for_a_week():
    r = c.get("/api/appointments/schedule.pdf",
              params={"date_from": "2026-09-01", "date_to": "2026-09-07"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_schedule_pdf_rejects_bad_range():
    assert c.get("/api/appointments/schedule.pdf",
                 params={"date_from": "2026-09-10", "date_to": "2026-09-01"}).status_code == 400
    assert c.get("/api/appointments/schedule.pdf",
                 params={"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code == 400


def test_schedule_pdf_works_on_empty_day():
    r = c.get("/api/appointments/schedule.pdf",
              params={"date_from": "2027-05-05", "date_to": "2027-05-05"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"   # пустой день — не ошибка
