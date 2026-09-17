from datetime import datetime, date
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..db import get_session
from ..models import Appointment, Reminder, Observation, Patient
from .. import clock

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
# «сегодня» берём из шва времени (clock), без хардкода


@router.get("/attention")
def attention(s: Session = Depends(get_session)):
    """Кто из всех пациентов требует внимания: просроченные контроли, показатели выше
    порога (любые, не только PSA), значения на подтверждении. Приоритезированный список."""
    import re
    from ..reference_data import parameters
    did = current_doctor_id()
    now = clock.now()
    patients = {p.id: p for p in s.exec(select(Patient).where(Patient.doctor_id == did)).all()}
    if not patients:
        return {"count": 0, "items": []}

    # числовые пороги параметров
    thr = {}
    for p in parameters():
        if p.get("threshold"):
            m = re.search(r"(\d+[.,]?\d*)", p["threshold"])
            if m:
                thr[p["code"]] = (float(m.group(1).replace(",", ".")), p.get("name", p["code"]))

    info = {pid: {"overdue": [], "above": [], "pending": 0} for pid in patients}

    for r in s.exec(select(Reminder).where(Reminder.doctor_id == did, Reminder.status == "open")).all():
        if r.patient_id in info and r.due_at and r.due_at < now:
            info[r.patient_id]["overdue"].append(r)

    for o in s.exec(select(Observation).where(Observation.status == "pending")).all():
        if o.patient_id in info:
            info[o.patient_id]["pending"] += 1

    latest = {}
    for o in s.exec(select(Observation).where(Observation.status == "confirmed")).all():
        if o.patient_id not in info or o.value_num is None:
            continue
        key = (o.patient_id, o.parameter_code)
        cur = latest.get(key)
        if not cur or (o.effective_date or date.min) >= (cur.effective_date or date.min):
            latest[key] = o
    for (pid, code), o in latest.items():
        t = thr.get(code)
        if t and o.value_num > t[0]:
            info[pid]["above"].append({"name": t[1], "value": o.value_num, "unit": o.unit, "threshold": t[0]})

    items = []
    for pid, d in info.items():
        reasons, prio = [], 0
        if d["overdue"]:
            md = max(int((now - r.due_at).days) for r in d["overdue"])
            reasons.append({"type": "overdue", "text": "Просрочен контроль" + (f" (на {md} дн.)" if md else "")})
            prio += 100 + md
        for a in d["above"]:
            reasons.append({"type": "above", "text": f"{a['name']} выше порога: {a['value']} {a['unit']}"})
            prio += 50
        if d["pending"]:
            reasons.append({"type": "pending", "text": f"{d['pending']} знач. на подтверждении"})
            prio += 10
        if reasons:
            items.append({"patient_id": pid, "name": patients[pid].short_name,
                          "reasons": reasons, "priority": prio})
    items.sort(key=lambda x: -x["priority"])
    return {"count": len(items), "items": items}


@router.get("")
def dashboard(s: Session = Depends(get_session)):
    # приёмы на сегодня
    appts = s.exec(select(Appointment).where(Appointment.doctor_id == current_doctor_id())).all()
    TODAY = clock.today()
    today_appts = [a for a in appts if a.starts_at.date() == TODAY]

    # просроченные напоминания
    rems = s.exec(select(Reminder).where(Reminder.doctor_id == current_doctor_id(),
                                         Reminder.status == "open")).all()
    overdue = [r for r in rems if r.due_at and r.due_at < clock.now()]

    # значения, ожидающие подтверждения
    pending = s.exec(select(Observation).where(Observation.status == "pending")).all()

    # подсказка: пациенты с PSA выше порога (аналог триггера Toki)
    obs = s.exec(select(Observation).where(Observation.parameter_code == "psa_total",
                                           Observation.status == "confirmed")).all()
    latest = {}
    for o in obs:
        if o.value_num is None:
            continue
        cur = latest.get(o.patient_id)
        if not cur or (o.effective_date or date.min) > (cur.effective_date or date.min):
            latest[o.patient_id] = o
    high_psa = [pid for pid, o in latest.items() if o.value_num > 4.0]

    suggestions = []
    if high_psa:
        suggestions.append({
            "icon": "ti-activity",
            "text": f"У {len(high_psa)} пациентов PSA выше порога — назначить контроль?",
            "action": "cohort",
        })
    if overdue:
        # эскалация: самый «застоявшийся» просроченный
        max_days = max(int((clock.now() - r.due_at).days) for r in overdue)
        level = "high" if max_days >= 7 else "mid" if max_days >= 2 else "low"
        suggestions.append({
            "icon": "ti-clock-exclamation",
            "text": f"{len(overdue)} напоминание(й) просрочено" + (f", до {max_days} дн." if max_days else ""),
            "action": "tasks", "level": level,
        })

    # недельная сводка (демо-неделя 09–15 марта)
    wk0, wk1 = clock.week_bounds()
    appts_week = [a for a in appts if wk0 <= a.starts_at.date() <= wk1]
    controls = [r for r in rems if r.kind == "control"]

    return {
        "date": TODAY.isoformat(),
        "today_appointments": len(today_appts),
        "overdue_reminders": len(overdue),
        "pending_observations": len(pending),
        "weekly": {
            "appointments": len(appts_week),
            "controls": len(controls),
            "overdue": len(overdue),
        },
        "suggestions": suggestions,
    }
