"""Логирование обезличенных событий использования для админ-аналитики."""
import json
from sqlmodel import Session
from ..models import AnalyticsEvent


def log_event(s: Session, event: str, props: dict | None = None, doctor_id: int | None = 1):
    """Пишет факт использования. В props НЕ должно быть персональных данных."""
    try:
        s.add(AnalyticsEvent(doctor_id=doctor_id, event=event,
                             props=json.dumps(props or {}, ensure_ascii=False)))
        s.commit()
    except Exception:
        s.rollback()
