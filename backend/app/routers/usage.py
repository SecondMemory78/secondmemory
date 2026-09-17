from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from ..db import get_session
from ..deps import current_doctor_id, require_admin
from ..models import UsageRecord, Doctor
from ..services.usage import limit_for, used_today, remaining_today, DEFAULT_LIMITS, KIND_LABEL
from .. import clock

KINDS = ["ocr", "stt", "llm"]

# ---- врач: сколько осталось сегодня ----
doctor = APIRouter(prefix="/api/usage", tags=["usage"])


@doctor.get("/today")
def today(s: Session = Depends(get_session)):
    did = current_doctor_id()
    return {k: {"used": used_today(s, did, k), "limit": limit_for(k),
                "remaining": remaining_today(s, did, k), "label": KIND_LABEL[k]} for k in KINDS}


# ---- админ: аналитика расхода ----
admin = APIRouter(prefix="/api/admin/usage", tags=["admin-usage"],
                  dependencies=[Depends(require_admin)])


def _period_start(period: str):
    if period == "day":
        d = clock.today(); return datetime(d.year, d.month, d.day)
    days = 7 if period == "week" else 30
    return clock.now() - timedelta(days=days)


@admin.get("/summary")
def summary(period: str = "day", s: Session = Depends(get_session)):
    start = _period_start(period)
    rows = s.exec(select(UsageRecord.kind, func.coalesce(func.sum(UsageRecord.units), 0))
                  .where(UsageRecord.created_at >= start).group_by(UsageRecord.kind)).all()
    by_kind = {k: 0 for k in KINDS}
    for k, n in rows:
        by_kind[k] = int(n)
    active = s.exec(select(func.count(func.distinct(UsageRecord.doctor_id)))
                    .where(UsageRecord.created_at >= start)).one()
    return {"period": period, "by_kind": by_kind, "total": sum(by_kind.values()),
            "active_doctors": int(active or 0), "limits": DEFAULT_LIMITS,
            "labels": KIND_LABEL}


@admin.get("/by-doctor")
def by_doctor(period: str = "day", s: Session = Depends(get_session)):
    start = _period_start(period)
    docs = {d.id: d for d in s.exec(select(Doctor)).all()}
    agg = {}
    rows = s.exec(select(UsageRecord.doctor_id, UsageRecord.kind,
                         func.coalesce(func.sum(UsageRecord.units), 0))
                  .where(UsageRecord.created_at >= start)
                  .group_by(UsageRecord.doctor_id, UsageRecord.kind)).all()
    for did, kind, n in rows:
        agg.setdefault(did, {k: 0 for k in KINDS})[kind] = int(n)
    out = []
    for did, kinds in agg.items():
        d = docs.get(did)
        out.append({"doctor_id": did, "name": d.full_name if d else "—",
                    "email": d.email if d else "", **kinds,
                    "total": sum(kinds.values()),
                    # остаток на сегодня по каждому виду (для контроля лимитов)
                    "today": {k: {"used": used_today(s, did, k), "limit": limit_for(k)} for k in KINDS}})
    out.sort(key=lambda x: x["total"], reverse=True)
    return out


@admin.get("/daily")
def daily(days: int = 30, s: Session = Depends(get_session)):
    start = clock.now() - timedelta(days=days)
    rows = s.exec(select(func.date(UsageRecord.created_at), UsageRecord.kind,
                         func.coalesce(func.sum(UsageRecord.units), 0))
                  .where(UsageRecord.created_at >= start)
                  .group_by(func.date(UsageRecord.created_at), UsageRecord.kind)).all()
    series = {}
    for day, kind, n in rows:
        day = str(day)
        series.setdefault(day, {"date": day, "ocr": 0, "stt": 0, "llm": 0})[kind] = int(n)
    return sorted(series.values(), key=lambda x: x["date"])


@admin.get("/cost")
def cost_by_doctor(s: Session = Depends(get_session)):
    """Прогнозная стоимость расхода ИИ за месяц по врачам + порог тревоги."""
    from ..services.ai_cost import month_cost_by_doctor, alert_threshold, DEFAULT_PRICE, price_for
    return {"threshold_rub": alert_threshold(),
            "prices": {k: price_for(k) for k in DEFAULT_PRICE},
            "doctors": month_cost_by_doctor(s)}


@admin.post("/cost/check")
def cost_check(s: Session = Depends(get_session)):
    """Пересчитать и создать уведомления по превышению порога расхода (дедуп по месяцу)."""
    from ..services.ai_cost import check_cost_alerts
    return {"alerts_created": check_cost_alerts(s)}
