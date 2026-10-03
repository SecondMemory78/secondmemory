from datetime import datetime, date, timedelta
from ..deps import current_doctor_id
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..db import get_session
from ..models import Appointment, Reminder, Observation, Patient
from .. import clock

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
# «сегодня» берём из шва времени (clock), без хардкода


@router.get("/digest")
def digest(s: Session = Depends(get_session)):
    """Сводка на сегодня: расписание, просроченное, кто требует внимания и
    почему. То же, что приходит утренним уведомлением, но подробнее и с
    переходами в карты."""
    from ..services.digest import build
    return build(s)


@router.get("/attention")
def attention(s: Session = Depends(get_session)):
    """Кто из всех пациентов требует внимания: просроченные контроли, показатели выше
    порога (любые, не только PSA), значения на подтверждении. Приоритезированный список."""
    import re
    from ..reference_data import parameters
    did = current_doctor_id()
    now = clock.now()
    patients = {p.id: p for p in s.exec(select(Patient).where(Patient.doctor_id == did,
                                                              Patient.is_training == False)).all()}
    if not patients:
        return {"count": 0, "items": []}

    # числовые пороги параметров
    thr = {}
    for p in parameters():
        if p.get("threshold"):
            m = re.search(r"(\d+[.,]?\d*)", p["threshold"])
            if m:
                thr[p["code"]] = (float(m.group(1).replace(",", ".")), p.get("name", p["code"]))

    info = {pid: {"overdue": [], "above": [], "pending": 0, "no_consent": False} for pid in patients}

    # согласие 152-ФЗ: без него приём вести нельзя — это самый блокирующий пункт
    from ..models import PatientConsent
    granted = set()
    for cns in s.exec(select(PatientConsent).where(
            PatientConsent.patient_id.in_(list(patients.keys())))).all():
        if cns.status == "granted":
            granted.add(cns.patient_id)
    for pid in info:
        info[pid]["no_consent"] = pid not in granted

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
        if d["no_consent"]:
            reasons.append({"type": "no_consent", "text": "Нет согласия — приём заблокирован"})
            prio += 200
        if reasons:
            items.append({"patient_id": pid, "name": patients[pid].short_name,
                          "reasons": reasons, "priority": prio})
    items.sort(key=lambda x: -x["priority"])
    return {"count": len(items), "items": items}


@router.get("")
def dashboard(s: Session = Depends(get_session)):
    # приёмы на сегодня
    # Отменённые приёмы в счётчики НЕ идут: список приёмов их не показывает
    # (см. routers/appointments), и врач видел «на этой неделе 8 приёмов» при
    # одном живом — остальные были отменены во время правок расписания.
    appts = [a for a in s.exec(
        select(Appointment).where(Appointment.doctor_id == current_doctor_id())).all()
        if a.status != "cancelled"]
    TODAY = clock.today()
    today_appts = [a for a in appts if a.starts_at.date() == TODAY]

    # просроченные напоминания
    rems = s.exec(select(Reminder).where(Reminder.doctor_id == current_doctor_id(),
                                         Reminder.status == "open")).all()
    overdue = [r for r in rems if r.due_at and r.due_at < clock.now()]

    # id пациентов этого врача — чтобы не увидеть чужие данные (тот же класс, что IDOR)
    own_patient_ids = set(s.exec(select(Patient.id).where(
        Patient.doctor_id == current_doctor_id())).all())

    # значения, ожидающие подтверждения
    pending = s.exec(select(Observation).where(Observation.status == "pending")).all()
    pending = [o for o in pending if o.patient_id in own_patient_ids]

    # подсказка: пациенты с PSA выше порога (аналог триггера Toki)
    obs = s.exec(select(Observation).where(Observation.parameter_code == "psa_total",
                                           Observation.status == "confirmed")).all()
    obs = [o for o in obs if o.patient_id in own_patient_ids]
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


@router.get("/my-stats")
def my_stats(days: int = 90, s: Session = Depends(get_session)):
    """Личная статистика врача: его собственный приём, никуда не уходит.

    Считаем то, что врач реально может использовать: сколько приёмов провёл,
    сколько пациентов не дошло (и в какие дни это чаще), объём картотеки,
    как идут задачи. Это НЕ продуктовая телеметрия — там обезличенные счётчики.
    """
    from ..models import Reminder, Appointment, Patient, Note
    did = current_doctor_id()
    now = clock.now()
    start = now - timedelta(days=max(7, min(days, 365)))

    appts = s.exec(select(Appointment).where(
        Appointment.doctor_id == did, Appointment.starts_at >= start)).all()
    past = [a for a in appts if a.starts_at <= now]
    done = [a for a in past if a.status == "done"]
    no_show = [a for a in past if a.status == "no_show"]
    cancelled = [a for a in past if a.status == "cancelled"]
    upcoming = [a for a in appts if a.starts_at > now and a.status == "planned"]

    # в какие дни недели чаще не доходят — врачу видно, когда ставить важное
    WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    by_wd = {w: {"total": 0, "no_show": 0} for w in WD}
    for a in past:
        w = WD[a.starts_at.weekday()]
        by_wd[w]["total"] += 1
        if a.status == "no_show":
            by_wd[w]["no_show"] += 1

    patients = s.exec(select(Patient).where(Patient.doctor_id == did,
                                            Patient.is_training == False)).all()
    new_patients = [p for p in patients if p.created_at >= start]

    rem = s.exec(select(Reminder).where(Reminder.doctor_id == did)).all()
    open_tasks = [r for r in rem if r.status == "open"]
    overdue = [r for r in open_tasks if r.due_at and r.due_at < now]
    done_tasks = [r for r in rem if r.status == "done" and r.completed_at
                  and r.completed_at >= start]

    notes_cnt = len(s.exec(select(Note).where(
        Note.patient_id.in_([p.id for p in patients]))).all()) if patients else 0

    finished = len(done) + len(no_show)
    return {
        "period_days": (now - start).days,
        "appointments": {
            "total": len(past), "done": len(done), "no_show": len(no_show),
            "cancelled": len(cancelled), "upcoming": len(upcoming),
            "no_show_rate": round(len(no_show) / finished * 100) if finished else 0,
        },
        "by_weekday": [{"day": w, **by_wd[w]} for w in WD],
        "patients": {"total": len(patients), "new": len(new_patients), "notes": notes_cnt},
        "tasks": {"open": len(open_tasks), "overdue": len(overdue), "done": len(done_tasks)},
    }
