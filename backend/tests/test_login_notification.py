"""Оповещение о входе: письмо + уведомление в приложении при входе с НОВОГО
устройства; повторный вход с того же устройства не спамит."""
import os, tempfile, uuid
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from fastapi.testclient import TestClient
from app.main import app
from app import seed
from app.db import engine
from app.models import Doctor, Notification, LoginCode
from sqlmodel import Session, select
seed.run()
c = TestClient(app)


def _email():
    return f"log_{uuid.uuid4().hex[:8]}@x.ru"


def _reg(email):
    c.post("/api/auth/register", json={"email": email, "phone": "+7900"+uuid.uuid4().hex[:7].translate(str.maketrans("abcdef","012345")),
                                       "password": "goodpass1", "full_name": "N"})


def _login(email, dev):
    from app.services import ratelimit
    ratelimit._hits.clear()   # снимаем cooldown отправки кода между входами в тесте
    c.post("/api/auth/login", json={"email": email, "password": "goodpass1", "device_id": dev})
    with Session(engine) as s:
        lc = s.exec(select(LoginCode).where(LoginCode.email == email).order_by(LoginCode.id.desc())).first()
    return c.post("/api/auth/verify", json={"email": email, "code": lc.code, "device_id": dev}).json()


def _sec_notifs(email):
    with Session(engine) as s:
        d = s.exec(select(Doctor).where(Doctor.email == email)).first()
        return s.exec(select(Notification).where(Notification.doctor_id == d.id,
                                                 Notification.kind == "security")).all()


def test_new_device_login_creates_notification():
    em = _email(); _reg(em)
    _login(em, "devA")
    notifs = _sec_notifs(em)
    assert len(notifs) >= 1
    assert "Новый вход" in notifs[0].text


def test_same_device_relogin_no_spam():
    em = _email(); _reg(em)
    _login(em, "devX")
    n1 = len(_sec_notifs(em))
    from app.services import ratelimit
    ratelimit._hits.clear()
    r = c.post("/api/auth/login", json={"email": em, "password": "goodpass1", "device_id": "devX"})
    assert r.json().get("code_required") is False   # known device → сразу токен
    n2 = len(_sec_notifs(em))
    assert n2 == n1, "повторный вход с того же устройства не должен спамить"


def test_second_new_device_notifies():
    em = _email(); _reg(em)
    _login(em, "d1")
    n1 = len(_sec_notifs(em))
    _login(em, "d2")   # другое устройство
    n2 = len(_sec_notifs(em))
    assert n2 == n1 + 1
