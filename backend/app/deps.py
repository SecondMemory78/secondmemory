"""Швы доступа.

current_doctor_id() — единая точка «кто сейчас врач». Значение кладётся в
контекст запроса ASGI-middleware из Bearer-токена. Заменяет захардкоженный
DOCTOR_ID=1 во всех роутерах.

Dev-режим (AUTH_OPTIONAL=1): без токена берётся демо-врач из базы — чтобы
фронт работал во время миграции на реальный вход.
"""
import os
import contextvars
from datetime import datetime
from fastapi import Header, HTTPException, Request
from sqlmodel import Session, select
from .db import engine
from .models import AuthSession, Doctor

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dev-admin-token")
AUTH_OPTIONAL = os.getenv("AUTH_OPTIONAL", "1") == "1"

_doctor_id = contextvars.ContextVar("doctor_id", default=None)


def set_current_doctor_id(value):
    _doctor_id.set(value)


def current_doctor_id() -> int:
    v = _doctor_id.get()
    if v is not None:
        return v
    if AUTH_OPTIONAL:
        with Session(engine) as s:
            d = s.exec(select(Doctor)).first()
            did = d.id if d else 1
        _doctor_id.set(did)
        return did
    raise HTTPException(401, "Не авторизовано")


def resolve_doctor_id_from_token(token: str):
    if not token:
        return None
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with Session(engine) as s:
        sess = s.exec(select(AuthSession).where(AuthSession.token_hash == token_hash)).first()
        if sess and sess.expires_at > datetime.utcnow():
            return sess.doctor_id
    return None


def require_admin(request: Request = None, x_admin_token: str = Header(default="")):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Неверный админ-токен")
    # журнал действий администрации (не логируем сам просмотр журнала — иначе шум)
    try:
        if request is not None and not request.url.path.endswith("/admin/audit"):
            from .models import AdminAudit
            with Session(engine) as s:
                s.add(AdminAudit(action=f"{request.method} {request.url.path}",
                                 detail=str(request.url.query or "")))
                s.commit()
    except Exception:
        pass      # журналирование не должно ломать сам запрос
