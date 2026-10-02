"""Связь журнала ИИ с решением врача.

Журнал фиксирует, что предложил ассистент. Но половина смысла — в том, что
врач сделал потом: подтвердил, исправил или отклонил. Без этой половины на
вопрос «почему в карте оказалось это значение» ответить нельзя: видно, что
ассистент предложил, и не видно, на чём основано решение.

ТЗ требует именно пары: результат извлечения и последующее подтверждение или
исправление.
"""
from datetime import datetime

from sqlmodel import Session, select

from .. import clock
from ..deps import current_doctor_id
from ..models import AssistantAction

CONFIRMED = "confirmed"
EDITED = "edited"
REJECTED = "rejected"


def mark_outcome(s: Session, entity_type: str, entity_id: int, outcome: str) -> int:
    """Отмечает в журнале, чем закончилось предложение ассистента.

    Возвращает число обновлённых записей. Если предложение делал не ассистент
    (врач внёс руками), записей не найдётся — это нормально, не ошибка.
    """
    rows = s.exec(select(AssistantAction).where(
        AssistantAction.doctor_id == current_doctor_id(),
        AssistantAction.entity_type == entity_type,
        AssistantAction.entity_id == entity_id,
        AssistantAction.outcome == "")).all()
    for r in rows:
        r.outcome = outcome
        r.outcome_at = clock.now()
        s.add(r)
    if rows:
        s.commit()
    return len(rows)


def chain(s: Session, entity_type: str, entity_id: int) -> list[dict]:
    """Цепочка по объекту карты: что сказал врач, как это разобрали, чем
    закончилось. То, что показываем, когда нужно объяснить происхождение."""
    rows = s.exec(select(AssistantAction).where(
        AssistantAction.doctor_id == current_doctor_id(),
        AssistantAction.entity_type == entity_type,
        AssistantAction.entity_id == entity_id)).all()
    out = []
    for r in sorted(rows, key=lambda x: x.created_at):
        out.append({
            "at": r.created_at.isoformat(),
            "channel": r.channel,                 # голосом или текстом
            "said": r.input_text,                 # что сказал врач
            "engine": r.engine,                   # правила или модель
            "engine_version": r.engine_version,
            "answer": r.message,                  # что ответил ассистент
            "outcome": r.outcome or "ожидает решения врача",
            "outcome_at": r.outcome_at.isoformat() if r.outcome_at else None,
        })
    return out
