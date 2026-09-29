"""Баг №3: Doctor.timezone реально применяется к тихим часам.

Фиксируем «сейчас» = 12:00 в дефолтной зоне (Europe/Moscow, UTC+3). Для врача в
Asia/Novosibirsk (UTC+7) это уже 16:00. Тихие часы 15–17 должны быть активны для
новосибирского врача и НЕ активны для московского при одном и том же моменте.
"""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import datetime
from app import seed, clock
from app.services import alerts as alerts_svc
from app.models import NotificationPreference

seed.run()


def test_hour_in_respects_timezone():
    with clock.frozen(datetime(2026, 6, 15, 12, 0, 0)):   # 12:00 МСК
        assert clock.hour_in("Europe/Moscow") == 12
        assert clock.hour_in("Asia/Novosibirsk") == 16    # +4 к Москве
        assert clock.hour_in(None) == 12                  # дефолт = серверная зона


def test_quiet_hours_use_doctor_timezone():
    prefs = NotificationPreference(doctor_id=999, quiet_hours_start=15, quiet_hours_end=17)
    with clock.frozen(datetime(2026, 6, 15, 12, 0, 0)):   # 12:00 МСК → 16:00 в Новосибирске
        # московский врач: 12:00 — не тихие часы
        assert alerts_svc.in_quiet_hours(prefs, tz="Europe/Moscow") is False
        # новосибирский врач: 16:00 — тихие часы активны
        assert alerts_svc.in_quiet_hours(prefs, tz="Asia/Novosibirsk") is True


def test_quiet_hours_default_zone_when_tz_missing():
    prefs = NotificationPreference(doctor_id=999, quiet_hours_start=11, quiet_hours_end=13)
    with clock.frozen(datetime(2026, 6, 15, 12, 0, 0)):
        assert alerts_svc.in_quiet_hours(prefs, tz=None) is True    # 12:00 в дефолтной зоне
