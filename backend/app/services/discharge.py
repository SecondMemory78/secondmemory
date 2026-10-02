"""Сборка выписки по эпизоду.

Главная мысль: документ собирается ТОЛЬКО из того, что подтверждено, а всё
остальное не исчезает молча — оно попадает в панель исключённого с причиной.

Почему это важнее самой сборки. Врач подписывает выписку своим именем. Если
значение не вошло, потому что ждало подтверждения или по нему был конфликт,
он должен об этом знать ДО подписи, а не узнать от пациента через месяц.
Молчаливый пропуск в медицинском документе хуже, чем пропуск с пометкой.

Второе правило, из ТЗ: раздел, по которому данных нет, не печатается вовсе.
Никаких «без особенностей» и «состояние удовлетворительное» — такие фразы
выглядят как выполненный осмотр, которого не было.
"""
from __future__ import annotations

import json
from datetime import date

from sqlmodel import Session, select

from .. import clock
from ..models import (Device, Discharge, Encounter, Observation, Patient,
                      PatientDiagnosis, Prescription, Procedure)

# Причины исключения — словами врача, а не кодами.
WHY_PENDING = "ждёт подтверждения врача"
WHY_CONFLICT = "есть противоречащие значения"
WHY_NO_DATE = "не указана дата"
WHY_UNCONFIRMED = "предложено ассистентом, не подтверждено"
WHY_CANCELLED = "отменено"
WHY_OUT_OF_EPISODE = "относится к другому периоду"
WHY_PATIENT_WORDS = "со слов пациента, не подтверждено документом"


def build_draft(s: Session, encounter_id: int) -> dict:
    """Собирает разделы выписки и список исключённого."""
    enc = s.get(Encounter, encounter_id)
    if not enc:
        raise ValueError("Эпизод не найден")
    pid = enc.patient_id
    patient = s.get(Patient, pid)

    sections: dict = {}
    excluded: list = []

    # Границы эпизода. Выписка — документ ПО ЭПИЗОДУ: без этого в неё попадала
    # вся история пациента, включая анализы двухлетней давности. Берём то, что
    # привязано к эпизоду, а при отсутствии привязки — то, что попало в его
    # сроки: часть данных вносится до того, как эпизод открыт.
    start = (enc.started_at.date() if enc.started_at else None)
    end = (enc.closed_at.date() if enc.closed_at else clock.today())

    # Данные вне сроков эпизода не выбрасываются молча. Но и перечислять их
    # поимённо нельзя — у пациента могут быть годы наблюдения, и панель
    # исключённого превратится в простыню. Поэтому одна строка на вид данных.
    out_of_episode = {"операции": 0, "показатели": 0}

    def in_episode(entity_encounter_id, when) -> bool:
        if entity_encounter_id == encounter_id:
            return True
        if entity_encounter_id is not None:
            return False                 # принадлежит другому эпизоду
        if when is None or start is None:
            return False
        return start <= when <= end

    def drop(what: str, why: str, detail: str = ""):
        excluded.append({"what": what, "why": why, "detail": detail})

    # ── диагнозы ────────────────────────────────────────────────────────────
    dx = s.exec(select(PatientDiagnosis).where(
        PatientDiagnosis.patient_id == pid)).all()
    active_dx = []
    for d in dx:
        if d.status != "active":
            continue
        if not d.confirmed:
            drop("Диагноз " + (d.code or d.title), WHY_UNCONFIRMED)
            continue
        active_dx.append(d)
    primary = next((d for d in active_dx if d.is_primary), None)
    if primary:
        sections["diagnosis_main"] = f"{primary.code} {primary.wording or primary.title}".strip()
    others = [d for d in active_dx if not d.is_primary]
    if others:
        sections["diagnosis_other"] = [
            f"{d.code} {d.wording or d.title}".strip() for d in others]

    # ── операции ────────────────────────────────────────────────────────────
    procs = s.exec(select(Procedure).where(Procedure.patient_id == pid)).all()
    done = []
    for p in procs:
        # Сначала точные причины, потом рамка эпизода: «не указана дата»
        # говорит врачу больше, чем «вне сроков», и чинится иначе.
        if p.status == "cancelled":
            drop("Операция " + p.name, WHY_CANCELLED)
            continue
        if not p.confirmed:
            drop("Операция " + p.name, WHY_UNCONFIRMED)
            continue
        if not p.performed_at:
            drop("Операция " + p.name, WHY_NO_DATE)
            continue
        if not in_episode(p.encounter_id, p.performed_at):
            out_of_episode["операции"] += 1
            continue
        done.append(p)
    if done:
        sections["procedures"] = [
            {"name": p.name, "side": p.side, "date": p.performed_at.isoformat(),
             "surgeon": p.surgeon, "outcome": p.outcome,
             # Пустое поле осложнений НЕ означает «осложнений не было».
             "complications": p.complications}
            for p in sorted(done, key=lambda x: x.performed_at)]

    # ── обследования ────────────────────────────────────────────────────────
    from .integrity import conflicting_observations
    conflicted = conflicting_observations(s, pid)
    obs = s.exec(select(Observation).where(Observation.patient_id == pid)).all()
    taken = []
    for o in obs:
        if o.status == "pending":
            drop("Показатель " + o.parameter_code, WHY_PENDING)
            continue
        if o.provenance == "patient_words":
            # В выписку такое не идёт, но врач должен знать, что оно есть:
            # это анамнез, а не результат.
            drop("Показатель " + o.parameter_code, WHY_PATIENT_WORDS)
            continue
        if o.parameter_code in conflicted:
            drop("Показатель " + o.parameter_code, WHY_CONFLICT)
            continue
        if not o.effective_date:
            drop("Показатель " + o.parameter_code, WHY_NO_DATE)
            continue
        if not in_episode(o.encounter_id, o.effective_date):
            out_of_episode["показатели"] += 1
            continue
        taken.append(o)
    if taken:
        from ..reference_data import parameter_label
        sections["investigations"] = [
            {"code": o.parameter_code, "label": parameter_label(o.parameter_code),
             "value": o.value_num if o.value_num is not None else o.value_text,
             "unit": o.unit, "date": o.effective_date.isoformat()}
            for o in sorted(taken, key=lambda x: x.effective_date)]

    # ── назначения при выписке ──────────────────────────────────────────────
    rx = s.exec(select(Prescription).where(Prescription.patient_id == pid)).all()
    active_rx = []
    for r in rx:
        if r.status == "cancelled":
            continue                        # отменённое — не пропуск, а норма
        if not r.confirmed:
            drop("Назначение " + (r.drug_name or ""), WHY_UNCONFIRMED)
            continue
        if r.status == "active":
            active_rx.append(r)
    if active_rx:
        sections["orders"] = [
            {"name": r.drug_name, "dose": r.dose, "frequency": r.frequency,
             "duration": r.duration, "category": r.category,
             "instruction": r.instruction} for r in active_rx]

    # ── устройства, которые остаются с пациентом ────────────────────────────
    devs = [d for d in s.exec(select(Device).where(
        Device.patient_id == pid)).all() if d.active]
    if devs:
        sections["devices"] = [
            {"kind": d.kind, "side": d.side, "label": d.device_label,
             "installed_at": d.installed_at.isoformat() if d.installed_at else None,
             "due_at": d.due_at.isoformat() if d.due_at else None} for d in devs]

    # ── шапка ───────────────────────────────────────────────────────────────
    sections["patient"] = {
        "name": patient.short_name if patient else "",
        "birth_date": patient.birth_date.isoformat() if patient and patient.birth_date else None,
    }
    sections["encounter"] = {
        "type": enc.type, "reason": enc.reason,
        "opened_at": enc.started_at.isoformat() if enc.started_at else None,
        "closed_at": enc.closed_at.isoformat() if enc.closed_at else None,
    }

    for what, n in out_of_episode.items():
        if n:
            drop(f"{what.capitalize()} вне сроков эпизода: {n}", WHY_OUT_OF_EPISODE,
                 "выписка собирается по одному эпизоду")

    return {"sections": sections, "excluded": excluded}


def checks(s: Session, d: Discharge) -> list[dict]:
    """Проверки перед подписанием. Это ПРЕДУПРЕЖДЕНИЯ, а не запреты: врач может
    подписать документ и с ними, но должен их увидеть."""
    sections = json.loads(d.sections or "{}")
    excluded = json.loads(d.excluded or "[]")
    out = []

    def warn(code: str, text: str):
        out.append({"code": code, "text": text})

    if not sections.get("diagnosis_main"):
        warn("D1", "Не указан основной диагноз")
    if not sections.get("investigations"):
        warn("D2", "В выписке нет ни одного обследования")
    if not sections.get("orders"):
        warn("D3", "Нет назначений при выписке — так и задумано?")

    for dev in sections.get("devices", []):
        if not dev.get("due_at"):
            warn("D4", "У устройства, которое остаётся с пациентом, не указан "
                       "срок замены или удаления")
        if not dev.get("installed_at"):
            warn("D5", "У устройства не указана дата установки")

    pending = [x for x in excluded if x["why"] == WHY_PENDING]
    if pending:
        warn("D6", f"Не вошло из-за ожидания подтверждения: {len(pending)}. "
                   f"Подтвердите нужное до подписания")
    conflicts = [x for x in excluded if x["why"] == WHY_CONFLICT]
    if conflicts:
        warn("D7", f"Не вошло из-за противоречий в данных: {len(conflicts)}")
    nodate = [x for x in excluded if x["why"] == WHY_NO_DATE]
    if nodate:
        warn("D8", f"Не вошло из-за отсутствия даты: {len(nodate)}")

    enc = sections.get("encounter") or {}
    if enc.get("type") == "hospitalization" and not enc.get("closed_at"):
        warn("D9", "Госпитализация ещё не закрыта")
    return out
