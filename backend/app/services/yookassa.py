"""Клиент ЮKassa. Честный фолбэк: без YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY реальный
платёж НЕ создаётся — вызывающий код (routers/billing.py) в этом случае активирует
подписку сразу в dev-режиме, явно это помечая, а не притворяясь оплатой.
"""
import os
import uuid
import requests


def configured() -> bool:
    return bool(os.getenv("YOOKASSA_SHOP_ID") and os.getenv("YOOKASSA_SECRET_KEY"))


def create_payment(amount_rub: int, description: str, return_url: str,
                   receipt_email: str, metadata: dict | None = None) -> dict | None:
    """Создать платёж в ЮKassa. Возвращает {id, confirmation_url} или None при ошибке/не настроено.
    metadata (doctor_id, plan) возвращается в вебхуке payment.succeeded — по ней активируем подписку.
    Чек 54-ФЗ формируется автоматически по переданному receipt (email плательщика обязателен)."""
    if not configured():
        return None
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret = os.getenv("YOOKASSA_SECRET_KEY")
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description,
        "metadata": metadata or {},
        "receipt": {
            "customer": {"email": receipt_email},
            "items": [{"description": description, "quantity": "1.00",
                       "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
                       "vat_code": int(os.getenv("YOOKASSA_VAT_CODE", "1")),
                       "payment_mode": "full_payment", "payment_subject": "service"}],
        },
    }
    try:
        r = requests.post("https://api.yookassa.ru/v3/payments", json=payload,
                          auth=(shop_id, secret), timeout=10,
                          headers={"Idempotence-Key": str(uuid.uuid4())})
        r.raise_for_status()
        data = r.json()
        return {"id": data["id"], "confirmation_url": data["confirmation"]["confirmation_url"]}
    except Exception:
        return None


def get_payment(payment_id: str) -> dict | None:
    """Проверка платежа ОБРАТНЫМ запросом к API ЮKassa (не доверяем телу вебхука).
    Возвращает {status, amount_rub, metadata} или None (не настроено/ошибка/не найден).
    Это защищает от поддельных уведомлений: подтверждение берём у самой ЮKassa."""
    if not configured():
        return None
    import os as _os
    shop_id = _os.getenv("YOOKASSA_SHOP_ID")
    secret = _os.getenv("YOOKASSA_SECRET_KEY")
    try:
        r = requests.get(f"https://api.yookassa.ru/v3/payments/{payment_id}",
                         auth=(shop_id, secret), timeout=10)
        r.raise_for_status()
        d = r.json()
        return {"status": d.get("status"),
                "amount_rub": float(d.get("amount", {}).get("value", 0) or 0),
                "metadata": d.get("metadata", {}) or {}}
    except Exception:
        return None
