"""Единый шов сериализации ORM-объектов (T2).

Проблема: SQLModel.model_dump() читает __dict__, который ПУСТ у «протухшего»
(expired) объекта после commit — и возвращает {}. Баг всплывал трижды
(reminders, triggers). Заплатки через s.refresh() лечили симптом, не причину.

Решение: dump() читает поля через getattr — доступ к атрибуту подгружает данные
из БД даже у expired-объекта (в отличие от model_dump, читающего __dict__).
Это делает сериализацию безопасной независимо от того, refreshнут объект или нет.
"""
from typing import Any, Optional


def dump(obj: Any) -> Optional[dict]:
    if obj is None:
        return None
    return {name: getattr(obj, name) for name in type(obj).model_fields}


def dump_all(objs) -> list[dict]:
    return [dump(o) for o in objs]
