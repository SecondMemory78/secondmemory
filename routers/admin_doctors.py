"""Админ/поддержка: карточки аккаунтов ВРАЧЕЙ (не пациентов!).

Осознанно ограничено данными самого врача: имя, контакты, специализация,
подписка, 2FA, устройства/сессии. Данные пациентов сюда НЕ попадают — это
отдельный, более чувствительный уровень доступа (обсуждается отдельно).

Сброс пароля НЕ показывает и НЕ задаёт пароль: админ лишь запускает штатную
процедуру /forgot (письмо со ссылкой уходит врачу на его почту). Так админ
никогда не знает и не устанавливает пароль врача.
"""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..deps import require_admin
from .. import clock
from pydantic import BaseModel
from ..models import Doctor, AuthSession, PasswordReset, Subscription
from ..services.billing import active_subscription
from ..services.email import send_email, email_configured
from ..security import new_token, sha256_hex
from ..deps import AUTH_OPTIONAL

router = APIRouter(prefix="/api/admin/doctors", tags=["admin-doctors"],
                   dependencies=[Depends(require_admin)])


def _sub_status(s: Session, doctor_id: int) -> dict:
    sub = active_subscription(s, doctor_id)
    if not sub:
        return {"active": False, "plan": None, "until": None}
    return {"active": True, "plan": sub.plan, "until": sub.period_end.isoformat()}


@router.get("")
def list_doctors(q: str = "", s: Session = Depends(get_session)):
    """Список врачей для поддержки. Поиск по имени/почте/телефону."""
    rows = s.exec(select(Doctor).order_by(Doctor.created_at.desc())).all()
    ql = q.strip().lower()
    if ql:
        rows = [d for d in rows if ql in f"{d.full_name} {d.email} {d.phone}".lower()]
    out = []
    for d in rows:
        sub = _sub_status(s, d.id)
        out.append({"id": d.id, "full_name": d.full_name, "email": d.email,
                    "phone": d.phone, "specialty": d.specialty, "role": d.role,
                    "is_demo": d.is_demo, "totp_enabled": d.totp_enabled,
                    "created_at": d.created_at.isoformat(),
                    "subscription": sub})
    return out


@router.get("/{doctor_id}")
def doctor_detail(doctor_id: int, s: Session = Depends(get_session)):
    d = s.get(Doctor, doctor_id)
    if not d:
        raise HTTPException(404, "Врач не найден")
    # активные сессии/устройства (для «помогите со входом»); токены не отдаём — их и нет в открытом виде
    now = clock.now()
    sessions = s.exec(select(AuthSession).where(AuthSession.doctor_id == doctor_id)
                      .order_by(AuthSession.created_at.desc())).all()
    devices = [{"device_id": (a.device_id or "")[:12], "user_agent": a.user_agent,
                "remembered": a.remembered, "active": a.expires_at > now,
                "created_at": a.created_at.isoformat(),
                "expires_at": a.expires_at.isoformat()} for a in sessions[:20]]
    return {"id": d.id, "full_name": d.full_name, "email": d.email, "phone": d.phone,
            "specialty": d.specialty, "license_no": d.license_no, "role": d.role,
            "is_demo": d.is_demo, "totp_enabled": d.totp_enabled,
            "timezone": d.timezone, "created_at": d.created_at.isoformat(),
            "subscription": _sub_status(s, doctor_id),
            "active_sessions": sum(1 for a in sessions if a.expires_at > now),
            "devices": devices}


@router.post("/{doctor_id}/password-reset")
def trigger_password_reset(doctor_id: int, s: Session = Depends(get_session)):
    """Запустить сброс пароля: письмо со ссылкой уходит ВРАЧУ на его почту.
    Админ не видит и не задаёт пароль. Возвращаем только факт отправки."""
    d = s.get(Doctor, doctor_id)
    if not d:
        raise HTTPException(404, "Врач не найден")
    if not d.email:
        raise HTTPException(400, "У врача не указана почта — сброс по ссылке невозможен")
    token = new_token()
    s.add(PasswordReset(email=d.email.lower(), token_hash=sha256_hex(token),
                        expires_at=clock.now() + timedelta(minutes=30)))
    s.commit()
    send_email(d.email, "Сброс пароля — Вторая память",
               f"Поддержка инициировала сброс пароля по вашему обращению.\n"
               f"Код для сброса пароля: {token}\nДействует 30 минут. "
               f"Если вы не обращались — проигнорируйте письмо.")
    resp = {"ok": True, "sent_to": d.email}
    if AUTH_OPTIONAL and not email_configured():
        resp["dev_token"] = token       # в деве почты нет — отдаём токен, чтобы протестировать
    return resp


# ── Доступ вручную ──────────────────────────────────────────────────────────
# Пока оплата не подключена, а пробного периода нет, доступ выдаётся руками:
# тестировщику, врачу-партнёру, первым пилотным врачам, при возврате денег.
# Раньше это делалось вставкой в базу через psql — не та операция, которую
# стоит выполнять руками на живом сервере.

class GrantIn(BaseModel):
    days: int = 30
    note: str = ""


@router.post("/{doctor_id}/subscription")
def grant_access(doctor_id: int, body: GrantIn, s: Session = Depends(get_session)):
    """Выдать или продлить доступ на N дней. Отражается в журнале администрации."""
    doc = s.get(Doctor, doctor_id)
    if not doc:
        raise HTTPException(404, "Врач не найден")
    if not 1 <= body.days <= 3650:
        raise HTTPException(400, "Срок должен быть от 1 до 3650 дней")

    current = active_subscription(s, doctor_id)
    base = current.period_end if current else clock.now()
    if current:
        current.status = "cancelled"          # старую закрываем, новую открываем на продлённый срок
        s.add(current)
    sub = Subscription(
        doctor_id=doctor_id, plan="manual", status="active",
        period_start=clock.now(), period_end=base + timedelta(days=body.days),
        amount=0, auto_renew=False,
        # Номер платежа уникален в базе, поэтому одной метки времени мало:
        # два доступа, выданных в одну секунду, упирались бы в ограничение.
        payment_id=(f"manual:{doctor_id}:{clock.now():%Y%m%d%H%M%S}:{secrets.token_hex(3)}"
                    + (f":{body.note[:40]}" if body.note else "")),
    )
    s.add(sub); s.commit(); s.refresh(sub)
    return {"ok": True, "until": sub.period_end.isoformat(),
            "days": body.days, "extended": bool(current)}


@router.delete("/{doctor_id}/subscription")
def revoke_access(doctor_id: int, s: Session = Depends(get_session)):
    """Отозвать доступ: врач остаётся в системе, но работает только на просмотр."""
    doc = s.get(Doctor, doctor_id)
    if not doc:
        raise HTTPException(404, "Врач не найден")
    sub = active_subscription(s, doctor_id)
    if not sub:
        return {"ok": True, "changed": False}
    sub.status = "cancelled"
    sub.period_end = clock.now()
    s.add(sub); s.commit()
    return {"ok": True, "changed": True}
