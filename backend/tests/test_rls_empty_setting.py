"""Пустая строка в параметре изоляции не должна ронять запросы.

На сервере /api/notifications то падал с 500, то отвечал 200. Ошибка:
invalid input syntax for type integer: "". Причина не в id врача, а в политике
изоляции: она приводила current_setting('app.current_doctor_id') к int, а этот
параметр после отката транзакции возвращается к ПУСТОЙ СТРОКЕ, а не к NULL.
Подключения берутся из пула — отсюда и «то падает, то нет».
"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from app.services import rls
from app.deps import set_current_doctor_id, current_doctor_id


def test_политика_защищена_от_пустой_строки():
    for cond in (rls._DOCTOR_MATCH, rls._CHILD_MATCH):
        assert "NULLIF(current_setting('app.current_doctor_id', true), '')::int" in cond, \
            "приведение к int без NULLIF — падает на пустой строке"


def test_пустая_строка_в_контексте_становится_none():
    set_current_doctor_id("")
    from app.deps import _doctor_id
    assert _doctor_id.get() is None


def test_мусор_в_контексте_не_уезжает_в_запрос():
    for junk in ("abc", None, [], {}):
        set_current_doctor_id(junk)
        from app.deps import _doctor_id
        assert _doctor_id.get() is None, f"{junk!r} не отфильтрован"


def test_число_строкой_приводится():
    set_current_doctor_id("7")
    assert current_doctor_id() == 7
    assert isinstance(current_doctor_id(), int)


def test_scope_никогда_не_ставит_пустую_строку():
    """Проверяем сам расчёт значения, без обращения к Postgres."""
    captured = {}

    class FakeSession:
        def get_bind(self):
            class E:
                class dialect:
                    name = "postgresql"
            return E()

        def execute(self, stmt, params=None):
            if params and "d" in params:
                captured["d"] = params["d"]

    for value in ("", None, "abc", 5, "5"):
        rls.set_session_scope(FakeSession(), value)
        assert captured["d"] != "", f"{value!r} дал пустую строку"
        int(captured["d"])          # обязано приводиться к числу
