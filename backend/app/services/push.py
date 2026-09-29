"""Web Push — отправка уведомлений на устройства врача/админа.

Работает на обеих платформах: Android/desktop (Chrome и др.) и iPhone (Safari, при
условии, что приложение добавлено на экран «Домой» — стандарт с iOS 16.4).

Текст пуша — обезличенный (идёт через серверы Apple/Google). Клик ведёт в приложение
на центр уведомлений (см. фронт), а не сразу в карту — дополнительный слой приватности.

VAPID-ключи: приватный в env (VAPID_PRIVATE_KEY), публичный отдаётся фронту (не секрет).
Без ключей отправка не выполняется (honest fallback) — код и подписки готовы, доставку
включает появление ключей + боевой HTTPS-домен.
"""
import os
import json
import logging
from sqlmodel import Session, select
from ..models import PushSubscription, PushDelivery

log = logging.getLogger("push")


def vapid_public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "")


def _vapid_private_key() -> str:
    return os.getenv("VAPID_PRIVATE_KEY", "")


def configured() -> bool:
    return bool(vapid_public_key() and _vapid_private_key())


def _claims() -> dict:
    # subject — контакт администратора для push-сервисов (требование VAPID)
    return {"sub": "mailto:" + os.getenv("VAPID_SUBJECT_EMAIL", "admin@vtoraya-pamyat.ru")}


def _guess_platform(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua or "ios" in ua:
        return "ios"
    if "android" in ua:
        return "android"
    if ua:
        return "desktop"
    return "unknown"


def send_to_subscription(sub: PushSubscription, payload: dict) -> tuple[bool, int | None, str]:
    """Отправка одной подписке. Возвращает (ok, status_code, error).
    Коды 404/410 = подписка мертва (устройство отписалось) — вызывающий её удалит."""
    if not configured():
        return False, None, "vapid_not_configured"
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        return False, None, f"pywebpush_missing:{e}"
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint,
                               "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_vapid_private_key(),
            vapid_claims=dict(_claims()),
            timeout=10,
        )
        return True, 201, ""
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return False, code, str(e)[:200]
    except Exception as e:
        return False, None, str(e)[:200]


def push_to_doctor(s: Session, doctor_id: int, kind: str, title: str, body: str,
                   url: str = "/notifications") -> dict:
    """Отправить пуш на ВСЕ устройства врача. Мёртвые подписки удаляем. Пишем журнал."""
    subs = s.exec(select(PushSubscription).where(
        PushSubscription.doctor_id == doctor_id,
        PushSubscription.is_admin_channel == False)).all()
    return _dispatch(s, subs, doctor_id, kind, title, body, url)


def push_to_admin(s: Session, kind: str, title: str, body: str,
                  url: str = "/") -> dict:
    subs = s.exec(select(PushSubscription).where(
        PushSubscription.is_admin_channel == True)).all()
    return _dispatch(s, subs, None, kind, title, body, url)


def _dispatch(s, subs, doctor_id, kind, title, body, url) -> dict:
    payload = {"title": title, "body": body, "url": url, "kind": kind}
    sent, failed = 0, 0
    for sub in subs:
        ok, code, err = send_to_subscription(sub, payload)
        platform = _guess_platform(sub.user_agent)
        s.add(PushDelivery(doctor_id=doctor_id, kind=kind, platform=platform,
                           ok=ok, status_code=code, error=err))
        if ok:
            sent += 1
        else:
            failed += 1
            if code in (404, 410):        # подписка мертва — убираем
                s.delete(sub)
    s.commit()
    return {"sent": sent, "failed": failed, "total": len(subs)}
