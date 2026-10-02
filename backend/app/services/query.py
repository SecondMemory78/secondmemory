"""Вопросы к картотеке на обычном языке.

Как это устроено и почему именно так.

Модель НЕ отвечает на вопрос и НЕ пишет запрос к базе. Она переводит вопрос в
набор условий из заранее утверждённого словаря — и всё. Условия проверяются
нашим кодом: неизвестное поле отбрасывается, значение приводится к нужному
типу. Поиск по базе выполняет наш код.

Так сделано потому, что врач принимает решения по тому, что увидит в ответе.
Если бы модель отвечала сама, она могла бы «вспомнить» пациента, которого нет,
или пропустить того, кто есть. Здесь она может ошибиться только в одном —
неверно понять вопрос, и это видно: вместе с ответом мы показываем, по каким
условиям искали.

Чего в базе нет — на то честно отвечаем «не знаю», а не придумываем.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from .. import clock
from ..deps import current_doctor_id
from ..models import Device, Observation, Patient, Prescription, Reminder

# ── Словарь условий ─────────────────────────────────────────────────────────
# Что вообще можно спросить. Всё, чего здесь нет, не выполняется.

DEVICE_KINDS = {"stent": "стент", "nephrostomy": "нефростома", "catheter": "катетер"}
SIDES = {"left": "слева", "right": "справа", "both": "с обеих сторон"}
OPS = {">": "больше", "<": "меньше", ">=": "не меньше", "<=": "не больше"}

FIELDS = {
    # устройства
    "device_kind": "тип устройства",
    "device_side": "сторона устройства",
    "device_due_before": "срок замены раньше даты",
    "device_due_after": "срок замены позже даты",
    # показатели
    "parameter_code": "код показателя",
    "value_op": "знак сравнения",
    "value": "значение",
    # контроли и задачи
    "control_overdue": "просроченный контроль",
    "control_parameter": "контроль по показателю",
    # назначения
    "order_contains": "в назначении есть слово",
    "order_pending": "назначение ещё не выполнено",
    # пациент
    "had_procedure": "были операции",
    "procedure_contains": "в названии операции есть слово",
    "diagnosis_code": "код диагноза",
    "age_min": "возраст от",
    "age_max": "возраст до",
}


@dataclass
class Query:
    filters: dict
    unsupported: list           # что в вопросе понято, но данных для этого нет
    by_model: bool = False      # условия подобрала модель, а не правила

    def human(self) -> str:
        """Как объяснить врачу, что именно искали."""
        parts = []
        f = self.filters
        if f.get("device_kind"):
            d = DEVICE_KINDS.get(f["device_kind"], f["device_kind"])
            if f.get("device_side"):
                d += " " + SIDES.get(f["device_side"], f["device_side"])
            parts.append(f"стоит {d}")
        if f.get("device_due_before"):
            parts.append(f"срок замены до {f['device_due_before']:%d.%m.%Y}")
        if f.get("parameter_code") and f.get("value") is not None:
            parts.append(f"{f['parameter_code']} {f.get('value_op', '>')} {f['value']}")
        if f.get("control_overdue"):
            parts.append("контроль просрочен")
        if f.get("control_parameter"):
            parts.append(f"назначен контроль: {f['control_parameter']}")
        if f.get("order_contains"):
            parts.append(f"в назначениях «{f['order_contains']}»")
        if f.get("procedure_contains"):
            parts.append(f"операция со словом «{f['procedure_contains']}»")
        elif f.get("had_procedure"):
            parts.append("были операции")
        if f.get("diagnosis_code"):
            parts.append(f"диагноз {f['diagnosis_code']}")
        if f.get("age_min"):
            parts.append(f"от {f['age_min']} лет")
        if f.get("age_max"):
            parts.append(f"до {f['age_max']} лет")
        return "; ".join(parts) or "без условий"


def validate(raw: dict) -> dict:
    """Оставляем только известные поля и приводим типы.

    Сюда приходит то, что предложила модель. Всё, чего нет в словаре,
    отбрасывается молча — это и есть защита от выдуманных условий.
    """
    out: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key not in FIELDS or value in (None, "", []):
            continue
        if key == "device_kind" and value not in DEVICE_KINDS:
            continue
        if key == "device_side" and value not in SIDES:
            continue
        if key == "value_op" and value not in OPS:
            continue
        if key in ("value",):
            try:
                value = float(str(value).replace(",", "."))
            except ValueError:
                continue
        if key in ("age_min", "age_max"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        if key in ("device_due_before", "device_due_after") and isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError:
                continue
        out[key] = value
    return out


# ── Поиск ───────────────────────────────────────────────────────────────────

def search(s: Session, filters: dict, limit: int = 50) -> list[dict]:
    """Выполняет условия по базе. Возвращает пациентов с пояснением, почему
    каждый попал в список — врач должен видеть основание, а не просто фамилию."""
    did = current_doctor_id()
    pts = s.exec(select(Patient).where(Patient.doctor_id == did,
                                       Patient.is_training == False)).all()  # noqa: E712
    today = clock.today()
    out = []

    for p in pts:
        why = []

        if filters.get("diagnosis_code"):
            if filters["diagnosis_code"].lower() not in (p.diagnosis_code or "").lower():
                continue
            why.append(p.diagnosis_code)

        if filters.get("age_min") or filters.get("age_max"):
            if not p.birth_date:
                continue
            age = today.year - p.birth_date.year
            if filters.get("age_min") and age < filters["age_min"]:
                continue
            if filters.get("age_max") and age > filters["age_max"]:
                continue
            why.append(f"{age} лет")

        if filters.get("device_kind") or filters.get("device_due_before") or filters.get("device_due_after"):
            devs = [d for d in s.exec(select(Device).where(
                Device.patient_id == p.id, Device.active == True)).all()]      # noqa: E712
            if filters.get("device_kind"):
                devs = [d for d in devs if d.kind == filters["device_kind"]]
            if filters.get("device_side"):
                devs = [d for d in devs if d.side == filters["device_side"]]
            if filters.get("device_due_before"):
                devs = [d for d in devs if d.due_at and d.due_at <= filters["device_due_before"]]
            if filters.get("device_due_after"):
                devs = [d for d in devs if d.due_at and d.due_at >= filters["device_due_after"]]
            if not devs:
                continue
            for d in devs:
                name = DEVICE_KINDS.get(d.kind, d.kind)
                if d.side:
                    name += " " + SIDES.get(d.side, d.side)
                why.append(name + (f", замена {d.due_at:%d.%m.%Y}" if d.due_at else ", срок не назначен"))

        if filters.get("parameter_code"):
            obs = [o for o in s.exec(select(Observation).where(
                Observation.patient_id == p.id,
                Observation.parameter_code == filters["parameter_code"])).all()
                if o.status != "pending" and o.value_num is not None]
            if not obs:
                continue
            last = sorted(obs, key=lambda o: o.effective_date or date.min)[-1]
            if filters.get("value") is not None:
                op = filters.get("value_op", ">")
                v, ref = last.value_num, filters["value"]
                ok = (v > ref if op == ">" else v < ref if op == "<"
                      else v >= ref if op == ">=" else v <= ref)
                if not ok:
                    continue
            why.append(f"{filters['parameter_code']} {last.value_num:g} {last.unit}".strip())

        if filters.get("control_overdue") or filters.get("control_parameter"):
            rems = [r for r in s.exec(select(Reminder).where(
                Reminder.patient_id == p.id, Reminder.status == "open")).all()]
            if filters.get("control_parameter"):
                word = filters["control_parameter"].lower()
                rems = [r for r in rems if word in (r.title or "").lower()
                        or word in (r.parameter_code or "").lower()]
            if filters.get("control_overdue"):
                rems = [r for r in rems if r.due_at and r.due_at.date() < today]
            if not rems:
                continue
            why.append("не выполнено: " + rems[0].title)

        if filters.get("had_procedure") or filters.get("procedure_contains"):
            from ..models import Procedure
            procs = [x for x in s.exec(select(Procedure).where(
                Procedure.patient_id == p.id)).all()
                if x.status != "cancelled" and x.confirmed]
            word = (filters.get("procedure_contains") or "").lower()
            if word:
                procs = [x for x in procs if word in (x.name or "").lower()]
            if not procs:
                continue
            last = sorted(procs, key=lambda x: (x.performed_at or date.min, x.id))[-1]
            when = f", {last.performed_at:%d.%m.%Y}" if last.performed_at else ""
            why.append(f"операция: {last.name}{when}")

        if filters.get("order_contains") or filters.get("order_pending"):
            word = (filters.get("order_contains") or "").lower()
            orders = [r for r in s.exec(select(Prescription).where(
                Prescription.patient_id == p.id)).all() if r.status in ("active", "planned")]
            if word:
                orders = [r for r in orders
                          if word in (r.drug_name or "").lower()
                          or word in (r.instruction or "").lower()]
            if not orders:
                continue
            why.append("назначено: " + (orders[0].instruction or orders[0].drug_name or ""))

        if not why and not filters:
            continue

        out.append({"patient_id": p.id, "name": p.short_name, "why": "; ".join(why)})
        if len(out) >= limit:
            break
    return out


# ── Вопрос → условия ────────────────────────────────────────────────────────
# Сначала правила: они дают предсказуемый результат и работают без ключей.
# Модель подключается только там, где правила не справились, и возвращает
# ровно те же поля словаря — её ответ всё равно проходит validate().

import re

_QUESTION_WORDS = ("кому", "у кого", "кто ", "какие", "каким", "у каких",
                   "когда", "сколько", "кого ")

_PARAM_WORDS = {
    "пса": "psa_total", "psa": "psa_total",
    "креатинин": "creatinine",
    "гемоглобин": "hemoglobin",
}

_NEXT_WEEK = ("на следующей неделе", "следующей неделе", "на этой неделе")


def _stem(word: str) -> str:
    """Грубая основа слова: отрезаем русские окончания. Нужна, чтобы «биопсию»
    из вопроса нашлось в назначении «Биопсия простаты»."""
    w = word.strip().lower()
    for end in ("иями", "ями", "ами", "ией", "ию", "ие", "ий", "ия", "ой", "ый",
                "ую", "ом", "ам", "ах", "ов", "ей", "е", "у", "ы", "и", "а", "я", "о"):
        if len(w) > 5 and w.endswith(end):
            return w[:-len(end)]
    return w


def looks_like_question(text: str) -> bool:
    low = (text or "").lower().strip()
    return low.endswith("?") or any(low.startswith(w) or f" {w}" in low
                                    for w in _QUESTION_WORDS)


def parse_question(text: str, use_model: bool = True) -> Query:
    """Переводит вопрос в условия. Что не поняли — честно в unsupported.

    Сначала правила: они предсказуемы, быстры и работают без ключей. Модель
    подключается ТОЛЬКО если правила ничего не поняли — и её ответ проходит
    тот же validate(), что и всё остальное. То есть модель может ошибиться с
    условиями, но не может ни придумать ответ, ни получить доступ к данным:
    она видит только текст вопроса и список разрешённых полей.
    """
    low = (text or "").lower()
    f: dict = {}
    unsupported: list[str] = []

    # устройства
    for kind, word in (("stent", "стент"), ("nephrostomy", "нефростом"),
                       ("catheter", "катетер")):
        if word in low:
            f["device_kind"] = kind
            break
    for side, word in (("left", "слева"), ("right", "справа")):
        if word in low:
            f["device_side"] = side

    # срок: «на следующей неделе», «на этой неделе»
    if any(w in low for w in _NEXT_WEEK):
        wk0, wk1 = clock.week_bounds()
        if "следующ" in low:
            wk0, wk1 = wk0 + timedelta(days=7), wk1 + timedelta(days=7)
        f["device_due_after"], f["device_due_before"] = wk0, wk1

    # показатель с порогом: «ПСА больше 10», «ПСА > 10»
    for word, code in _PARAM_WORDS.items():
        if word in low:
            m = re.search(rf"{word}\D{{0,20}}?(>=|<=|>|<|больше|выше|меньше|ниже)?\s*(\d+[.,]?\d*)", low)
            if m:
                f["parameter_code"] = code
                f["value"] = float(m.group(2).replace(",", "."))
                sign = (m.group(1) or ">").strip()
                f["value_op"] = {"больше": ">", "выше": ">", "меньше": "<",
                                 "ниже": "<"}.get(sign, sign if sign in OPS else ">")
            elif "контрол" in low:
                f["control_parameter"] = word
            break

    # контроль не выполнен
    if ("не выполнен" in low or "просроч" in low) and "контрол" in low:
        f["control_overdue"] = True
        f.pop("value", None)

    # ожидают процедуру: «ожидают биопсию простаты»
    m = re.search(r"ожида\w*\s+([а-яё]+)", low)
    if m:
        # Берём основу: в вопросе слово в падеже («биопсию»), а в назначении
        # оно в именительном («Биопсия»). Сравнение целиком не совпадёт.
        f["order_contains"] = _stem(m.group(1))
        f["order_pending"] = True

    # операции: «кого оперировали», «кому делали стентирование»
    if "операц" in low or "оперирова" in low:
        f["had_procedure"] = True
    m2 = re.search(r"(?:делали|сделали|проводили)\s+([а-яё]{4,})", low)
    if m2:
        f["procedure_contains"] = _stem(m2.group(1))

    # чего в базе нет — говорим прямо, а не делаем вид
    if "койк" in low or "стационар" in low or "госпитализ" in low:
        unsupported.append("кто сейчас в стационаре — таких данных в карте нет")

    # Защита стоит ПОСЛЕ всех условий, а не в середине: раньше она была выше
    # разбора операций, и добавленное ниже условие её обходило — вопрос «какая
    # последняя операция у пациента» снова начал отвечаться списком.
    if low.strip().startswith("когда") or "последний раз" in low or "последняя" in low:
        if not re.search(r"\b[а-яё]+(ов|ев|ин|ын|ский|ко|ук|ова|ева|ина)\b", low):
            unsupported.append("вопрос про конкретного пациента — назовите фамилию "
                               "или откройте карту")
            f.clear()

    filters = validate(f)
    by_model = False

    # Правила не справились — спросим модель. Без ключей parse_query вернёт
    # None, и поведение останется прежним.
    if not filters and not unsupported and use_model:
        from .ai import parse_query as model_query
        guess = model_query(text)
        if guess:
            filters = validate(guess)
            if filters:
                by_model = True

    return Query(filters=filters, unsupported=unsupported, by_model=by_model)


def ask(s: Session, text: str) -> dict:
    """Полный путь: вопрос → условия → поиск → ответ врачу."""
    q = parse_question(text)

    if not q.filters:
        msg = "Не понял, что искать."
        if q.unsupported:
            msg = q.unsupported[0].capitalize() + "."
        return {"intent": "query", "ok": False, "message": msg,
                "filters": {}, "explain": "", "items": [], "unsupported": q.unsupported}

    items = search(s, q.filters)
    if items:
        msg = f"Нашёл: {len(items)}. Условия — {q.human()}."
    else:
        msg = f"Никого не нашёл по условиям: {q.human()}."
    if q.unsupported:
        msg += " " + q.unsupported[0].capitalize() + "."
    return {"intent": "query", "ok": True, "message": msg,
            "engine": "model" if q.by_model else "rules",
            "filters": {k: str(v) for k, v in q.filters.items()},
            "explain": q.human(), "items": items, "unsupported": q.unsupported}
