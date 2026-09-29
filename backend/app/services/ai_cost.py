"""Оценка стоимости расхода ИИ и алерт при превышении прогноза.

Считаем по ПРОГНОЗНЫМ ценникам (наши расчёты, вынесены в env — при появлении
реальных цен Yandex меняются без правки кода). Точность вырастет с боевыми ключами.

Единицы учёта у нас = операции (1 запись = 1 единица), поэтому цена задаётся
«за операцию» усреднённо:
  ocr — распознавание файла (Vision), stt — расшифровка речи (SpeechKit),
  llm — команда/структурирование (YandexGPT).
"""
import os
from datetime import timedelta
from sqlmodel import Session, select, func
from ..models import UsageRecord, Doctor
from .. import clock

# Прогнозные цены за одну операцию, руб. (усреднённо, по нашим расчётам)
DEFAULT_PRICE = {"ocr": 0.15, "stt": 0.35, "llm": 0.50}
# Порог тревоги на врача в месяц, руб. — когда прогноз расхода приближается к марже
DEFAULT_ALERT_RUB = 2500


def price_for(kind: str) -> float:
    return float(os.getenv(f"AI_PRICE_{kind.upper()}", DEFAULT_PRICE.get(kind, 0.5)))


def alert_threshold() -> int:
    return int(os.getenv("AI_COST_ALERT_RUB", str(DEFAULT_ALERT_RUB)))


def _month_start():
    d = clock.today()
    from datetime import datetime
    return datetime(d.year, d.month, 1)


def month_cost_by_doctor(s: Session) -> list[dict]:
    """Прогнозная стоимость расхода ИИ за текущий месяц по каждому врачу."""
    start = _month_start()
    rows = s.exec(select(UsageRecord.doctor_id, UsageRecord.kind,
                         func.coalesce(func.sum(UsageRecord.units), 0))
                  .where(UsageRecord.created_at >= start)
                  .group_by(UsageRecord.doctor_id, UsageRecord.kind)).all()
    agg = {}
    for did, kind, n in rows:
        agg.setdefault(did, {"ocr": 0, "stt": 0, "llm": 0})
        if kind in agg[did]:
            agg[did][kind] = int(n)
    docs = {d.id: d for d in s.exec(select(Doctor)).all()}
    out = []
    for did, kinds in agg.items():
        cost = sum(kinds[k] * price_for(k) for k in kinds)
        d = docs.get(did)
        out.append({"doctor_id": did, "name": d.full_name if d else "—",
                    "ops": kinds, "cost_rub": round(cost, 2),
                    "over": cost >= alert_threshold()})
    out.sort(key=lambda x: -x["cost_rub"])
    return out


def check_cost_alerts(s: Session):
    """Создаёт уведомления администрации по врачам, чей прогноз расхода превысил порог.
    Дедуп по месяцу и врачу (одно уведомление на врача в месяц)."""
    from ..models import Notification
    month = clock.today().strftime("%Y-%m")
    thr = alert_threshold()
    created = 0
    for row in month_cost_by_doctor(s):
        if not row["over"]:
            continue
        key = f"cost_alert:{row['doctor_id']}:{month}"
        exists = s.exec(select(Notification).where(Notification.dedup_key == key)).first()
        if exists:
            continue
        # уведомление врачу-администратору (doctor_id=None → в общий поток админа)
        s.add(Notification(doctor_id=row["doctor_id"], kind="limit", level="warn",
                           text=f"Расход ИИ за месяц по врачу «{row['name']}» достиг "
                                f"{row['cost_rub']:.0f} ₽ (порог {thr} ₽).",
                           dedup_key=key))
        created += 1
    if created:
        s.commit()
    return created
