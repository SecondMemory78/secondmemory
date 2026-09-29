"""Готовые списки пациентов (пресеты C01–C05, ТЗ §11).

Список — сохранённый фильтр по ПОДТВЕРЖДЁННЫМ данным и незавершённым действиям.
Показывает причину попадания, срок, переход в карту. Окна «7 дней»/«2 дня» —
настройки интерфейса, НЕ интервалы лечения. Сам факт попадания ничего не
назначает. Пациент в списке не дублируется, даже если причин несколько.

Здесь реализованы C03, C04, C05 — они выразимы на текущей модели без её правок.
C01 (контроль ПСА с привязкой результата к назначению) и C02 (устройства:
катетер/стент/нефростома) добавляются отдельно, когда под них доводится модель.
"""
from datetime import timedelta
from sqlmodel import Session, select
from .. import clock
from ..models import Patient, Reminder, Observation, Encounter, SickLeave

WINDOW_7 = 7      # окно интерфейса для «до сегодня + 7 дней»
WINDOW_2 = 2      # окно интерфейса для «до сегодня + 2 дня»


def _patients_map(s: Session, doctor_id: int) -> dict:
    return {p.id: p for p in s.exec(select(Patient).where(
        Patient.doctor_id == doctor_id, Patient.is_training == False)).all()}


def _c03_repeat_unconfirmed(s: Session, doctor_id: int, pts: dict) -> list:
    """C03. Срок согласованного повтора прошёл; нет подтверждения визита, отмены
    или переноса. «Не явился» — только при явной отметке; иначе «Нет подтверждения»."""
    from ..models import Appointment
    now = clock.now()
    out = {}
    rows = s.exec(select(Appointment).where(
        Appointment.doctor_id == doctor_id,
        Appointment.kind == "repeat",
        Appointment.status == "planned",       # не done (подтверждён) и не cancelled (отменён/перенесён)
        Appointment.starts_at < now)).all()
    for a in rows:
        if a.patient_id not in pts or a.patient_id in out:
            continue
        days = int((now - a.starts_at).days)
        out[a.patient_id] = {
            "patient_id": a.patient_id, "name": pts[a.patient_id].short_name,
            "due": a.starts_at.date().isoformat(),
            "reason": "Нет подтверждения повторного визита" + (f" (срок прошёл на {days} дн.)" if days else ""),
        }
    return list(out.values())


def _c04_awaiting_result(s: Session, doctor_id: int, pts: dict) -> list:
    """C04. Результат ожидается или получен, но не рассмотрен.
    «Не рассмотрен» = наблюдение со статусом pending (ждёт подтверждения врачом)."""
    out = {}
    rows = s.exec(select(Observation).where(Observation.status == "pending")).all()
    for o in rows:
        if o.patient_id not in pts or o.patient_id in out:
            continue
        out[o.patient_id] = {
            "patient_id": o.patient_id, "name": pts[o.patient_id].short_name,
            "due": o.effective_date.isoformat() if o.effective_date else None,
            "reason": "Получен результат — требуется разбор и подтверждение",
        }
    return list(out.values())


def _c05_discharge_sickleave(s: Session, doctor_id: int, pts: dict) -> list:
    """C05. План выписки или действие с больничным наступают до сегодня + 2 дня,
    включая просрочку. Незакрытый больничный остаётся после выписки."""
    now = clock.now()
    horizon = now + timedelta(days=WINDOW_2)
    out = {}

    def add(pid, reason, due):
        if pid not in pts:
            return
        if pid in out:
            out[pid]["reason"] += "; " + reason      # один пациент — одна строка, причины объединяем
        else:
            out[pid] = {"patient_id": pid, "name": pts[pid].short_name, "due": due, "reason": reason}

    # плановая выписка наступает (и ещё не выписан фактически)
    enc = s.exec(select(Encounter).where(
        Encounter.doctor_id == doctor_id,
        Encounter.type == "hospitalization",
        Encounter.status == "open")).all()
    for e in enc:
        if e.planned_discharge_at and not e.actual_discharge_at and e.planned_discharge_at <= horizon:
            add(e.patient_id, "Плановая выписка", e.planned_discharge_at.date().isoformat())

    # открытый/продлённый больничный (в т.ч. оставшийся после выписки)
    sl = s.exec(select(SickLeave).where(
        SickLeave.doctor_id == doctor_id,
        SickLeave.status != "closed")).all()
    for x in sl:
        add(x.patient_id, "Больничный не закрыт", x.opened_at.isoformat() if x.opened_at else None)

    return list(out.values())


def _c01_psa_control(s: Session, doctor_id: int, pts: dict) -> list:
    """C01. В плане врача есть контроль ПСА со сроком до сегодня+7 дней (включая
    просрочку) и нет ПОДТВЕРЖДЁННОГО результата, соответствующего назначению.
    Результат получен, но не оценён (pending) — это C04, здесь не показываем.
    Срок не задан → показываем с пометкой «Срок не задан»."""
    now = clock.now()
    horizon = now + timedelta(days=WINDOW_7)
    out = {}
    controls = s.exec(select(Reminder).where(
        Reminder.doctor_id == doctor_id,
        Reminder.kind == "control",
        Reminder.status == "open",
        Reminder.parameter_code == "psa_total")).all()
    for r in controls:
        if r.patient_id not in pts or r.patient_id in out:
            continue
        no_due = r.due_at is None
        if not no_due and r.due_at > horizon:
            continue                          # срок ещё далеко (дальше окна интерфейса)
        # есть ли подтверждённый результат ПСА после даты назначения?
        since = (r.due_at or r.created_at).date()
        confirmed = s.exec(select(Observation).where(
            Observation.patient_id == r.patient_id,
            Observation.parameter_code == "psa_total",
            Observation.status == "confirmed")).all()
        has_result = any(o.effective_date and o.effective_date >= since for o in confirmed)
        if has_result:
            continue                          # результат привязан к назначению → пункт закрыт
        reason = "Срок контроля ПСА не задан" if no_due else "Контроль ПСА — нет результата"
        out[r.patient_id] = {
            "patient_id": r.patient_id, "name": pts[r.patient_id].short_name,
            "due": None if no_due else r.due_at.date().isoformat(),
            "reason": reason,
        }
    return list(out.values())


def _c02_devices(s: Session, doctor_id: int, pts: dict) -> list:
    """C02. Активное устройство (катетер/стент/нефростома), у которого замена/удаление
    назначены до сегодня+7 дней (включая просрочку). Отдельно — «срок не задан».
    Закрывается подтверждённым действием по device_id (закрытые active=False сюда не
    попадают — реализовано в жизненном цикле). Пациент без дубля: несколько устройств
    сводятся в одну строку, конкретные изделия перечислены в причине."""
    from ..models import Device
    now = clock.now().date()
    horizon = now + timedelta(days=WINDOW_7)
    out = {}
    rows = s.exec(select(Device).where(
        Device.doctor_id == doctor_id, Device.active == True)).all()
    KIND_RU = {"catheter": "катетер", "stent": "стент", "nephrostomy": "нефростома"}
    for d in rows:
        if d.patient_id not in pts:
            continue
        no_due = d.due_at is None
        if not no_due and d.due_at > horizon:
            continue                          # срок ещё далеко
        label = KIND_RU.get(d.kind, d.kind) + (f" ({d.device_label})" if d.device_label else "")
        piece = f"{label} — срок не задан" if no_due else f"{label} — до {d.due_at.isoformat()}"
        rec = out.get(d.patient_id)
        # срок строки = ближайшая заданная дата среди устройств пациента
        due_val = None if no_due else d.due_at.isoformat()
        if rec:
            rec["_pieces"].append(piece)
            if due_val and (rec["due"] is None or due_val < rec["due"]):
                rec["due"] = due_val
        else:
            out[d.patient_id] = {"patient_id": d.patient_id, "name": pts[d.patient_id].short_name,
                                 "due": due_val, "_pieces": [piece]}
    result = []
    for rec in out.values():
        rec["reason"] = "Замена/удаление устройства: " + "; ".join(rec.pop("_pieces"))
        result.append(rec)
    return result


# Реестр доступных пресетов (порядок = порядок показа).
PRESETS = [
    ("C01", "Контроль ПСА", _c01_psa_control),
    ("C02", "Устройства (катетер/стент/нефростома)", _c02_devices),
    ("C03", "Повтор не подтверждён", _c03_repeat_unconfirmed),
    ("C04", "Ожидаем результат или разбор", _c04_awaiting_result),
    ("C05", "Выписка и больничный", _c05_discharge_sickleave),
]


def list_presets(s: Session, doctor_id: int) -> list:
    """Все пресеты со счётчиками (для экрана списков)."""
    pts = _patients_map(s, doctor_id)
    result = []
    for code, title, fn in PRESETS:
        items = fn(s, doctor_id, pts)
        result.append({"code": code, "title": title, "count": len(items)})
    return result


def preset_items(s: Session, doctor_id: int, code: str) -> dict | None:
    """Содержимое одного пресета по коду."""
    for c, title, fn in PRESETS:
        if c == code:
            pts = _patients_map(s, doctor_id)
            items = fn(s, doctor_id, pts)
            return {"code": c, "title": title, "count": len(items), "items": items}
    return None
