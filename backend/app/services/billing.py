"""Подписка: тарифы, продление, барьер записи для неоплативших.

Без активной подписки (кроме демо-аккаунта) врач может только просматривать
уже внесённые данные — вся запись блокируется SubscriptionGateMiddleware
(main.py), а не point-точечными проверками в роутерах: так надёжнее против
случайно забытого эндпоинта.
"""
import calendar
import os
from datetime import datetime
from sqlmodel import Session, select
from ..models import Subscription, Doctor
from .. import clock

BASE_PRICE = 6000        # руб./мес при тарифе на 1 месяц

PLANS = {
    "1m":  {"months": 1,  "discount": 0,  "label": "1 месяц"},
    "3m":  {"months": 3,  "discount": 10, "label": "3 месяца"},
    "6m":  {"months": 6,  "discount": 15, "label": "6 месяцев"},
    "12m": {"months": 12, "discount": 25, "label": "12 месяцев"},
}


def price_for(plan_key: str) -> int:
    p = PLANS[plan_key]
    return round(BASE_PRICE * p["months"] * (100 - p["discount"]) / 100)


def plans_public() -> list[dict]:
    return [{"key": k, "label": v["label"], "months": v["months"],
             "discount": v["discount"], "price": price_for(k),
             "price_per_month": round(price_for(k) / v["months"])}
            for k, v in PLANS.items()]


def add_months(dt: datetime, months: int) -> datetime:
    """Прибавить месяцы к дате, аккуратно обходя длину месяца (без доп. зависимостей)."""
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)


def is_demo_doctor(s: Session, doctor_id: int) -> bool:
    d = s.get(Doctor, doctor_id)
    return bool(d and d.is_demo)


def active_subscription(s: Session, doctor_id: int):
    row = s.exec(select(Subscription).where(
        Subscription.doctor_id == doctor_id, Subscription.status == "active")
        .order_by(Subscription.period_end.desc())).first()
    if row and row.period_end > clock.now():
        return row
    return None


def subscription_ok(s: Session, doctor_id: int) -> bool:
    return is_demo_doctor(s, doctor_id) or active_subscription(s, doctor_id) is not None


def apply_payment(s: Session, doctor_id: int, plan_key: str, payment_id: str = "") -> Subscription:
    """Активировать/продлить подписку. Если уже есть активная — продлеваем от её
    текущего конца (не теряем оплаченное время), иначе — от сегодня."""
    plan = PLANS[plan_key]
    current = active_subscription(s, doctor_id)
    base = current.period_end if current else clock.now()
    if current:
        current.status = "cancelled"           # закрываем старую запись, открываем новую на продлённый срок
        s.add(current)
    sub = Subscription(doctor_id=doctor_id, plan=plan_key, status="active",
                       period_start=clock.now(), period_end=add_months(base, plan["months"]),
                       amount=price_for(plan_key), payment_id=payment_id,
                       auto_renew=current.auto_renew if current else True)
    s.add(sub); s.commit(); s.refresh(sub)
    return sub


def yookassa_configured() -> bool:
    return bool(os.getenv("YOOKASSA_SHOP_ID") and os.getenv("YOOKASSA_SECRET_KEY"))
