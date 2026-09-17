"""Человеческие тексты уведомлений: склонение и формулировки будильников."""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from app.services.plural import count, plural


def test_plural_ru():
    assert count(1, "пациент", "пациента", "пациентов") == "1 пациент"
    assert count(2, "пациент", "пациента", "пациентов") == "2 пациента"
    assert count(5, "пациент", "пациента", "пациентов") == "5 пациентов"
    assert count(21, "задача", "задачи", "задач") == "21 задача"
    assert count(11, "задача", "задачи", "задач") == "11 задач"


def test_offset_human():
    from app.services.scheduler import _fmt_offset
    assert _fmt_offset(15) == "через 15 мин"
    assert _fmt_offset(60) == "через 1 час"
    assert _fmt_offset(120) == "через 2 часа"
    assert _fmt_offset(1440) == "через 1 день"
    assert _fmt_offset(2880) == "через 2 дня"
