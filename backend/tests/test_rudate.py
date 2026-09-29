"""Разбор времени так, как говорят врачи (а не «пятнадцать ноль-ноль»).

Фразы взяты из реальных жалоб на работу ассистента.
"""
import os, tempfile
os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
from datetime import datetime
from app.services.rudate import parse_datetime, parse_time
from app import clock


def setup_function():
    clock.set_fixed(datetime(2026, 9, 27, 14, 0))     # воскресенье 14:00


def teardown_function():
    clock.reset()


def test_hour_without_minutes():
    assert parse_time("запиши на 15 час в среду") == (15, 0)


def test_three_oclock_afternoon_is_15_not_3():
    """Главный баг: «в 3 часа дня» ставилось на 3 ночи."""
    assert parse_time("в 3 часа дня") == (15, 0)
    assert parse_datetime("запиши Иванова в 3 часа дня на среду") == datetime(2026, 9, 30, 15, 0)


def test_six_in_the_evening():
    assert parse_time("на 6 вечера") == (18, 0)
    assert parse_datetime("Поставь напоминание на 6 вечера заехать в магазин") \
        == datetime(2026, 9, 27, 18, 0)


def test_morning_and_night_are_not_shifted():
    assert parse_time("в 9 утра") == (9, 0)
    assert parse_time("в 3 ночи") == (3, 0)


def test_relative_minutes_and_hours():
    assert parse_datetime("позвонить через 20 минут") == datetime(2026, 9, 27, 14, 20)
    assert parse_datetime("перезвонить через 2 часа") == datetime(2026, 9, 27, 16, 0)


def test_words_instead_of_digits():
    assert parse_time("в три часа дня") == (15, 0)


def test_parts_of_day_alone():
    assert parse_time("заехать в магазин вечером") == (18, 0)
    assert parse_time("позвонить утром") == (9, 0)


def test_no_time_means_none_not_nine_am():
    """Молча подставлять 9:00 нельзя — лучше задача без срока."""
    assert parse_datetime("просто дело без срока") is None
    assert parse_time("просто дело без срока") is None


def test_time_only_rolls_to_tomorrow_if_passed():
    assert parse_datetime("в 9 утра") == datetime(2026, 9, 28, 9, 0)   # 9:00 уже прошло
    assert parse_datetime("в 18:00") == datetime(2026, 9, 27, 18, 0)   # ещё впереди


def test_weekday_is_next_future_one():
    assert parse_datetime("в среду в 15:00") == datetime(2026, 9, 30, 15, 0)


# ── название задачи без командной обвязки ───────────────────────────────────
def test_task_title_drops_command_and_time():
    from app.services.nlp import parse_reminder
    r = parse_reminder("Поставь напоминание на 6 вечера заехать в магазин")
    assert r["title"] == "заехать в магазин"
    assert r["due_at"].startswith("2026-09-27T18:00")


def test_urgent_phrase_sets_priority_and_relative_due():
    from app.services.nlp import parse_reminder
    r = parse_reminder("срочно позвонить человеку через 20 минут")
    assert r["title"] == "позвонить человеку"
    assert r["priority"] == 1
    assert r["due_at"].startswith("2026-09-27T14:20")


def test_plain_task_is_left_alone():
    from app.services.nlp import parse_reminder
    r = parse_reminder("заехать в магазин")
    assert r["title"] == "заехать в магазин" and r["due_at"] is None


def test_tag_still_becomes_project():
    from app.services.nlp import parse_reminder
    r = parse_reminder("созвон с командой в четверг #Работа")
    assert r["project"] == "Работа" and r["title"] == "созвон с командой"


# ── явные даты (жалоба: «не записывает на октябрь, ставит понедельник и час ночи») ──
def test_explicit_date_with_month_name():
    from datetime import datetime as dt
    assert parse_datetime("запиши Иванова на 20 октября в 15 часов") == dt(2026, 10, 20, 15, 0)


def test_day_number_is_not_read_as_hour():
    """«1 октября в 10 утра» раньше превращалось в 01:00 сегодня."""
    from datetime import datetime as dt
    assert parse_datetime("запиши Иванова на 1 октября в 10 утра") == dt(2026, 10, 1, 10, 0)


def test_numeric_date():
    from datetime import datetime as dt
    assert parse_datetime("приём 20.10 в 9:30") == dt(2026, 10, 20, 9, 30)


def test_bare_month_goes_to_its_first_day():
    from datetime import datetime as dt
    assert parse_datetime("запиши на октябрь") == dt(2026, 10, 1, 9, 0)


def test_month_root_does_not_match_random_word():
    """«заехать в магазин» не должно стать «в мае» — ловушка коротких корней."""
    assert parse_datetime("заехать в магазин") is None


def test_past_month_rolls_to_next_year():
    from datetime import datetime as dt
    assert parse_datetime("в мае") == dt(2027, 5, 1, 9, 0)
