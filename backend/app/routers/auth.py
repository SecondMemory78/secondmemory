"""Аутентификация (T4).

Схема (ADR-0001):
- register: email + пароль + ФИО + специальность.
- login: пароль верный + известное устройство → сразу токен; новое устройство → код на почту.
- verify: код + устройство → сессия (30 дней; 90, если «запомнить устройство»).
- me: текущий врач по Bearer-токену.

Отправка кода — заглушка: в dev код возвращается в ответе (dev_code). В проде —
письмо через почтовый провайдер (SMS позже).
"""
from datetime import datetime, timedelta
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db import get_session
from ..deps import AUTH_OPTIONAL, current_doctor_id
from ..models import Doctor, AuthSession, LoginCode, PasswordReset
from ..security import hash_password, verify_password, new_token, new_code, sha256_hex
from ..services.ratelimit import check as rl_check, reset as rl_reset
from ..services.email import send_email, email_configured

LOGIN_MAX = int(os.getenv("AUTH_LOGIN_MAX", "10"))
LOGIN_WINDOW = 300          # 10 попыток / 5 минут
VERIFY_MAX = int(os.getenv("AUTH_VERIFY_MAX", "5"))
VERIFY_WINDOW = 600         # 5 попыток кода / 10 минут


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"

router = APIRouter(prefix="/api/auth", tags=["auth"])
SPECIALTIES = ["Уролог", "Терапевт", "Хирург", "Кардиолог", "Невролог",
               "Эндокринолог", "Гинеколог", "Онколог", "Другое"]


class RegisterIn(BaseModel):
    email: str
    phone: str
    password: str
    full_name: str
    specialty: str = "Уролог"


class LoginIn(BaseModel):
    email: str
    password: str
    device_id: str = ""
    remember: bool = False


class VerifyIn(BaseModel):
    email: str
    code: str
    device_id: str = ""
    remember: bool = False


@router.get("/specialties")
def specialties():
    return SPECIALTIES


def _issue_session(s: Session, doctor: Doctor, device_id: str, remember: bool, user_agent: str = ""):
    days = 90 if remember else 30
    raw_token = new_token()
    sess = AuthSession(doctor_id=doctor.id, token_hash=sha256_hex(raw_token), device_id=device_id,
                       user_agent=(user_agent or "")[:200],
                       remembered=remember, expires_at=datetime.utcnow() + timedelta(days=days))
    s.add(sess); s.commit(); s.refresh(sess)
    return {"token": raw_token, "expires_at": sess.expires_at.isoformat(),
            "doctor": {"id": doctor.id, "full_name": doctor.full_name,
                       "specialty": doctor.specialty, "role": doctor.role, "email": doctor.email}}


def _send_code(s: Session, email: str):
    code = new_code()
    s.add(LoginCode(email=email, code=code,
                    expires_at=datetime.utcnow() + timedelta(minutes=15)))
    s.commit()
    send_email(email, "Код входа — Вторая память",
               f"Ваш код для входа: {code}\nКод действует 15 минут.")
    return code    # в проде уходит письмом; dev_code отдаём только если письма не настроены


def _dev_extra(code):
    """dev-подсказка: код в ответе только когда почта не настроена (dev)."""
    return {"dev_code": code} if (AUTH_OPTIONAL and not email_configured()) else {}


@router.post("/register")
def register(body: RegisterIn, s: Session = Depends(get_session)):
    phone = "".join(ch for ch in body.phone if ch.isdigit() or ch == "+")
    if len(phone) < 10:
        raise HTTPException(400, "Укажите телефон для регистрации")
    if s.exec(select(Doctor).where(Doctor.email == body.email.lower())).first():
        raise HTTPException(409, "Врач с такой почтой уже есть")
    if s.exec(select(Doctor).where(Doctor.phone == phone)).first():
        raise HTTPException(409, "Врач с таким телефоном уже зарегистрирован")
    doc = Doctor(full_name=body.full_name, specialty=body.specialty,
                 email=body.email.lower(), phone=phone,
                 password_hash=hash_password(body.password), role="doctor")
    s.add(doc); s.commit(); s.refresh(doc)
    code = _send_code(s, doc.email)
    return {"ok": True, "code_required": True, **_dev_extra(code)}


@router.post("/login")
def login(body: LoginIn, request: Request, s: Session = Depends(get_session)):
    ok, retry = rl_check(f"login:{body.email.lower()}:{_client(request)}", LOGIN_MAX, LOGIN_WINDOW)
    if not ok:
        raise HTTPException(429, f"Слишком много попыток входа. Повторите через {retry} с.")
    doc = s.exec(select(Doctor).where(Doctor.email == body.email.lower())).first()
    if not doc or not verify_password(body.password, doc.password_hash):
        raise HTTPException(401, "Неверная почта или пароль")
    rl_reset(f"login:{body.email.lower()}:{_client(request)}")     # успех — сброс счётчика
    # известное устройство с живой сессией → сразу токен
    if body.device_id:
        known = s.exec(select(AuthSession).where(
            AuthSession.doctor_id == doc.id, AuthSession.device_id == body.device_id)).all()
        if any(k.expires_at > datetime.utcnow() for k in known):
            return {"code_required": False, **_issue_session(s, doc, body.device_id, body.remember, request.headers.get("user-agent",""))}
    code = _send_code(s, doc.email)
    return {"code_required": True, **_dev_extra(code)}


@router.post("/verify")
def verify(body: VerifyIn, request: Request, s: Session = Depends(get_session)):
    ok, retry = rl_check(f"verify:{body.email.lower()}:{_client(request)}", VERIFY_MAX, VERIFY_WINDOW)
    if not ok:
        raise HTTPException(429, f"Слишком много попыток ввода кода. Повторите через {retry} с.")
    doc = s.exec(select(Doctor).where(Doctor.email == body.email.lower())).first()
    if not doc:
        raise HTTPException(404, "Врач не найден")
    row = s.exec(select(LoginCode).where(LoginCode.email == body.email.lower(),
                                         LoginCode.code == body.code)).first()
    if not row or row.expires_at < datetime.utcnow():
        raise HTTPException(401, "Код неверен или истёк")
    rl_reset(f"verify:{body.email.lower()}:{_client(request)}")     # верный код — сброс
    s.delete(row); s.commit()
    return {"code_required": False, **_issue_session(s, doc, body.device_id, body.remember, request.headers.get("user-agent",""))}


@router.post("/demo")
def demo_login(s: Session = Depends(get_session)):
    """Быстрый вход в демо (только в dev). Гарантирует наличие данных и выдаёт
    токен демо-врача — чтобы можно было сразу посмотреть заполненную базу."""
    if not AUTH_OPTIONAL:
        raise HTTPException(403, "Демо-вход отключён в этом окружении")
    from ..db import init_db
    init_db()                      # на случай пустой БД без прогона startup
    # если база пустая — заполняем демо-данными (идемпотентно)
    if not s.exec(select(Doctor)).first():
        from .. import seed
        seed.run()
    doc = s.exec(select(Doctor).where(Doctor.email == "doctor@demo.ru")).first() \
        or s.exec(select(Doctor)).first()
    return {"code_required": False, **_issue_session(s, doc, "demo-device", True)}


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    email: str
    token: str
    new_password: str


@router.post("/forgot")
def forgot(body: ForgotIn, request: Request, s: Session = Depends(get_session)):
    """Запрос сброса пароля. Ответ одинаковый независимо от наличия почты
    (защита от перебора существующих аккаунтов). Rate-limit."""
    ok, retry = rl_check(f"forgot:{_client(request)}", 10, 600)
    if not ok:
        raise HTTPException(429, f"Слишком много запросов. Повторите через {retry} с.")
    email = body.email.lower()
    doc = s.exec(select(Doctor).where(Doctor.email == email)).first()
    resp = {"ok": True}
    if doc:
        token = new_token()
        s.add(PasswordReset(email=email, token_hash=sha256_hex(token),
                            expires_at=datetime.utcnow() + timedelta(minutes=30)))
        s.commit()
        send_email(email, "Сброс пароля — Вторая память",
                   f"Код для сброса пароля: {token}\nДействует 30 минут. "
                   f"Если вы не запрашивали сброс — проигнорируйте письмо.")
        if AUTH_OPTIONAL and not email_configured():
            resp["dev_token"] = token
    return resp


@router.post("/reset")
def reset(body: ResetIn, request: Request, s: Session = Depends(get_session)):
    ok, retry = rl_check(f"reset:{_client(request)}", 10, 600)
    if not ok:
        raise HTTPException(429, f"Слишком много попыток. Повторите через {retry} с.")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Пароль должен быть не короче 8 символов")
    email = body.email.lower()
    row = s.exec(select(PasswordReset).where(
        PasswordReset.email == email, PasswordReset.token_hash == sha256_hex(body.token),
        PasswordReset.used == False)).first()
    if not row or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "Ссылка сброса неверна или истекла")
    doc = s.exec(select(Doctor).where(Doctor.email == email)).first()
    if not doc:
        raise HTTPException(404, "Врач не найден")
    doc.password_hash = hash_password(body.new_password)
    row.used = True
    s.add(doc); s.add(row)
    # безопасность: гасим все активные сессии этого врача
    for sess in s.exec(select(AuthSession).where(AuthSession.doctor_id == doc.id)).all():
        s.delete(sess)
    s.commit()
    return {"ok": True}


@router.get("/sessions")
def my_sessions(authorization: str = Header(default=""), s: Session = Depends(get_session)):
    """Список активных устройств врача. Текущее помечается current=true."""
    did = current_doctor_id()
    cur_hash = sha256_hex(authorization.replace("Bearer ", "").strip())
    rows = s.exec(select(AuthSession).where(AuthSession.doctor_id == did)
                  .order_by(AuthSession.created_at.desc())).all()
    now = datetime.utcnow()
    out = []
    for r in rows:
        if r.expires_at < now:
            continue
        out.append({"id": r.id, "device_id": r.device_id, "user_agent": r.user_agent,
                    "created_at": r.created_at.isoformat(), "expires_at": r.expires_at.isoformat(),
                    "current": r.token_hash == cur_hash})
    return out


@router.post("/sessions/{sid}/revoke")
def revoke_session(sid: int, s: Session = Depends(get_session)):
    """Выйти с конкретного устройства (напр. потерянного телефона)."""
    sess = s.get(AuthSession, sid)
    if sess and sess.doctor_id == current_doctor_id():
        s.delete(sess); s.commit()
    return {"ok": True}


@router.get("/me")
def me(authorization: str = Header(default=""), s: Session = Depends(get_session)):
    token = authorization.replace("Bearer ", "").strip()
    sess = s.exec(select(AuthSession).where(AuthSession.token_hash == sha256_hex(token))).first()
    if not sess or sess.expires_at < datetime.utcnow():
        raise HTTPException(401, "Сессия не найдена или истекла")
    doc = s.get(Doctor, sess.doctor_id)
    return {"id": doc.id, "full_name": doc.full_name, "specialty": doc.specialty,
            "role": doc.role, "email": doc.email}


@router.post("/logout")
def logout(authorization: str = Header(default=""), s: Session = Depends(get_session)):
    token = authorization.replace("Bearer ", "").strip()
    sess = s.exec(select(AuthSession).where(AuthSession.token_hash == sha256_hex(token))).first()
    if sess:
        s.delete(sess); s.commit()
    return {"ok": True}
