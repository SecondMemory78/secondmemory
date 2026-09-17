"""Подписка на Web Push (врач) и админ-канал (поддержка)."""
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import current_doctor_id, require_admin
from ..models import PushSubscription
from ..services.push import vapid_public_key, push_to_doctor, push_to_admin, configured

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-key")
def get_vapid_key():
    """Публичный VAPID-ключ для оформления подписки на фронте (не секрет)."""
    return {"key": vapid_public_key(), "configured": configured()}


class SubIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.post("/subscribe")
def subscribe(body: SubIn, request: Request, s: Session = Depends(get_session)):
    """Сохранить подписку браузера врача. Повтор того же endpoint не плодит дубли."""
    did = current_doctor_id()
    ua = request.headers.get("user-agent", "")
    ex = s.exec(select(PushSubscription).where(
        PushSubscription.endpoint == body.endpoint)).first()
    if ex:
        ex.doctor_id = did; ex.p256dh = body.p256dh; ex.auth = body.auth
        ex.user_agent = ua; ex.is_admin_channel = False; s.add(ex)
    else:
        s.add(PushSubscription(doctor_id=did, endpoint=body.endpoint, p256dh=body.p256dh,
                               auth=body.auth, user_agent=ua))
    s.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: SubIn, s: Session = Depends(get_session)):
    row = s.exec(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).first()
    if row:
        s.delete(row); s.commit()
    return {"ok": True}


@router.post("/test")
def send_test(s: Session = Depends(get_session)):
    """Тестовый пуш врачу — чтобы сразу убедиться, что доставка работает."""
    r = push_to_doctor(s, current_doctor_id(), "test",
                       "Готово!", "Уведомления подключены.")
    return r


# ── админ-канал поддержки ──
admin = APIRouter(prefix="/api/admin/push", tags=["admin-push"])


@admin.post("/subscribe")
def admin_subscribe(body: SubIn, request: Request, _: None = Depends(require_admin),
                    s: Session = Depends(get_session)):
    ua = request.headers.get("user-agent", "")
    ex = s.exec(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).first()
    if ex:
        ex.is_admin_channel = True; ex.doctor_id = None; ex.p256dh = body.p256dh
        ex.auth = body.auth; ex.user_agent = ua; s.add(ex)
    else:
        s.add(PushSubscription(doctor_id=None, is_admin_channel=True, endpoint=body.endpoint,
                               p256dh=body.p256dh, auth=body.auth, user_agent=ua))
    s.commit()
    return {"ok": True}


@admin.post("/test")
def admin_test(_: None = Depends(require_admin), s: Session = Depends(get_session)):
    return push_to_admin(s, "test", "Готово!", "Канал поддержки подключён.")


@admin.get("/health")
def push_health(s: Session = Depends(get_session), _: None = Depends(require_admin)):
    """Здоровье доставки push: активные подписки по платформам + статистика доставок за 7 дней."""
    from ..models import PushDelivery
    from datetime import timedelta
    from .. import clock
    subs = s.exec(select(PushSubscription)).all()
    by_platform = {"ios": 0, "android": 0, "desktop": 0, "unknown": 0}
    from ..services.push import _guess_platform
    for x in subs:
        by_platform[_guess_platform(x.user_agent)] = by_platform.get(_guess_platform(x.user_agent), 0) + 1
    start = clock.now() - timedelta(days=7)
    dl = s.exec(select(PushDelivery).where(PushDelivery.created_at >= start)).all()
    ok = sum(1 for d in dl if d.ok)
    fail = sum(1 for d in dl if not d.ok)
    recent_errors = [{"kind": d.kind, "platform": d.platform, "code": d.status_code,
                      "error": d.error, "at": d.created_at.isoformat()}
                     for d in sorted(dl, key=lambda x: x.id, reverse=True) if not d.ok][:20]
    total = ok + fail
    return {"subscriptions": len(subs), "by_platform": by_platform,
            "delivered_7d": ok, "failed_7d": fail,
            "success_rate": round(ok / total * 100, 1) if total else None,
            "admin_channel": sum(1 for x in subs if x.is_admin_channel),
            "recent_errors": recent_errors}
