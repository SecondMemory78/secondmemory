import os
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id
from ..models import Doctor, Subscription
from ..services.billing import (plans_public, PLANS, price_for, active_subscription,
                                subscription_ok, apply_payment, yookassa_configured)
from ..services import yookassa
from .. import clock

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/plans")
def plans():
    return plans_public()


@router.get("/status")
def status(s: Session = Depends(get_session)):
    did = current_doctor_id()
    d = s.get(Doctor, did)
    sub = active_subscription(s, did)
    ok = subscription_ok(s, did)
    days_left = max(0, (sub.period_end - clock.now()).days) if sub else 0
    return {"active": ok, "is_demo": bool(d and d.is_demo),
            "plan": sub.plan if sub else None,
            "period_end": sub.period_end.isoformat() if sub else None,
            "days_left": days_left, "auto_renew": sub.auto_renew if sub else False}


class SubscribeIn(BaseModel):
    plan: str


@router.post("/subscribe")
def subscribe(body: SubscribeIn, request: Request, s: Session = Depends(get_session)):
    if body.plan not in PLANS:
        raise HTTPException(400, "Неизвестный тариф")
    did = current_doctor_id()
    doc = s.get(Doctor, did)
    if not doc:
        raise HTTPException(404, "Врач не найден")

    if not yookassa_configured():
        # Без ключей ЮKassa реальная оплата невозможна.
        # В DEV (AUTH_OPTIONAL=1) — активируем сразу для отладки, явно помечая dev_mode.
        # В ПРОДЕ (AUTH_OPTIONAL=0) — это ошибка конфигурации: НЕ выдаём доступ бесплатно.
        from ..deps import AUTH_OPTIONAL
        if not AUTH_OPTIONAL:
            raise HTTPException(503, "Приём оплаты временно недоступен. Обратитесь в поддержку.")
        sub = apply_payment(s, did, body.plan, payment_id="dev-no-payment")
        return {"ok": True, "activated": True, "dev_mode": True,
                "period_end": sub.period_end.isoformat()}

    frontend = os.getenv("FRONTEND_URL", str(request.base_url).rstrip("/"))
    pay = yookassa.create_payment(
        price_for(body.plan), f"Подписка «Вторая память» — {PLANS[body.plan]['label']}",
        return_url=f"{frontend}/billing?paid=1", receipt_email=doc.email,
        metadata={"doctor_id": str(did), "plan": body.plan})
    if not pay:
        raise HTTPException(502, "Не удалось создать платёж. Попробуйте позже.")
    return {"ok": True, "activated": False, "confirmation_url": pay["confirmation_url"],
            "payment_id": pay["id"]}


@router.post("/webhook/yookassa")
async def webhook(request: Request, s: Session = Depends(get_session)):
    """Уведомление ЮKassa об оплате. НЕ доверяем телу: берём id платежа и
    перепроверяем его статус и сумму ОБРАТНЫМ запросом к API ЮKassa. Это защищает
    от поддельных уведомлений (иначе кто угодно активировал бы себе подписку)."""
    from ..services.yookassa import get_payment, configured as yk_conf
    from ..services.billing import price_for
    from ..models import Subscription
    body = await request.json()
    if body.get("event") != "payment.succeeded":
        return {"ok": True}
    payment_id = (body.get("object", {}) or {}).get("id", "")
    if not payment_id:
        raise HTTPException(400, "Нет id платежа")

    # если ключи ЮKassa не настроены — обрабатывать боевые вебхуки нельзя (иначе подделка)
    if not yk_conf():
        raise HTTPException(503, "Приём платежей не настроен")

    verified = get_payment(payment_id)          # ← подтверждение у самой ЮKassa
    if not verified or verified["status"] != "succeeded":
        raise HTTPException(400, "Платёж не подтверждён ЮKassa")

    meta = verified["metadata"]
    did, plan = meta.get("doctor_id"), meta.get("plan")
    if not did or plan not in PLANS:
        raise HTTPException(400, "Некорректные метаданные платежа")
    # сверяем, что оплаченная сумма соответствует тарифу (защита от подмены суммы)
    if abs(verified["amount_rub"] - price_for(plan)) > 0.01:
        raise HTTPException(400, "Сумма платежа не соответствует тарифу")
    # идемпотентность: этот платёж уже применён — не продлеваем повторно
    if s.exec(select(Subscription).where(Subscription.payment_id == payment_id)).first():
        return {"ok": True, "already": True}

    apply_payment(s, int(did), plan, payment_id=payment_id)
    return {"ok": True}


class RenewIn(BaseModel):
    enabled: bool


@router.post("/auto-renew")
def set_auto_renew(body: RenewIn, s: Session = Depends(get_session)):
    """ВНИМАНИЕ: сейчас хранит только НАМЕРЕНИЕ автопродления. Фактическое
    автосписание по истечении периода ещё не реализовано — для него нужен
    планировщик задач + сохранённый способ оплаты в ЮKassa (recurrent payments).
    Задача в списке к доделке ПЕРЕД боевым запуском."""
    sub = active_subscription(s, current_doctor_id())
    if not sub:
        raise HTTPException(404, "Активной подписки нет")
    sub.auto_renew = body.enabled
    s.add(sub); s.commit()
    return {"ok": True, "auto_renew": sub.auto_renew}
