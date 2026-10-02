"""Каталог действий приложения.

Зачем он нужен. Раньше каждое умение ассистента было отдельной веткой в коде:
добавить операцию в приложение — одно место, научить ей ассистента — другое.
Ассистент из-за этого навсегда отставал от интерфейса, а правила («писать
только с подтверждением», «триггеры не трогать») приходилось помнить и
повторять в каждой ветке. Забыл — дыра, и заметить её можно было только
глазами.

Теперь операция описывается ОДИН раз: имя, что ей нужно, кому она доступна и
требует ли подтверждения врача. Из этого описания кормятся интерфейс,
ассистент и будущие каналы (боты, запись приёма, импорт).

Главное правило, которое держит весь продукт: предложение ИИ не становится
записью в карте. Поэтому уровень доступа — не комментарий, а проверка в
единственном месте, через которое проходят все вызовы.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ── Уровни доступа ──────────────────────────────────────────────────────────
READ = "read"            # чтение: ассистенту можно без ограничений
# Операция меняет данные врача. Это НЕ значит «спросить разрешения на каждое
# действие»: запись на приём, задача и заметка как выполнялись сразу, так и
# выполняются. Значит это другое — у таких операций есть правила, записанные
# рядом с ними, и для медицинских данных правило такое: назначение создаётся
# предложением, показатель попадает в очередь на проверку.
WRITES = "writes"
DOCTOR_ONLY = "doctor"   # ассистенту запрещено вовсе, даже как предложение

LEVELS = (READ, WRITES, DOCTOR_ONLY)
CONFIRM = WRITES          # прежнее имя уровня, чтобы не ломать вызовы


@dataclass(frozen=True)
class Action:
    """Одна операция приложения."""

    name: str                       # patient.note, appointment.create, ...
    level: str                      # READ | WRITES | DOCTOR_ONLY
    title: str                      # как назвать врачу
    run: Optional[Callable] = None  # что выполнить; None — ещё не подключено
    args: tuple = ()                # обязательные аргументы
    why_doctor_only: str = ""       # почему запрещено ассистенту — для ответа врачу

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"{self.name}: неизвестный уровень доступа {self.level!r}")


_REGISTRY: dict[str, Action] = {}


def register(action: Action) -> Action:
    if action.name in _REGISTRY:
        raise ValueError(f"Действие {action.name} уже зарегистрировано")
    _REGISTRY[action.name] = action
    return action


def get(name: str) -> Optional[Action]:
    return _REGISTRY.get(name)


def all_actions() -> list[Action]:
    return sorted(_REGISTRY.values(), key=lambda a: a.name)


def for_assistant() -> list[Action]:
    """Что ассистент вправе предлагать или выполнять."""
    return [a for a in all_actions() if a.level != DOCTOR_ONLY]


class ActionDenied(Exception):
    """Ассистенту нельзя. Сообщение предназначено врачу."""


class ActionUnknown(Exception):
    """Такой операции в каталоге нет."""


def run(name: str, *, by: str = "doctor", **kwargs):
    """Единственный вход для выполнения действия.

    by="assistant" — вызов от ассистента: запрещённые операции отклоняются
    здесь, а не в семи местах. Операции уровня CONFIRM ассистент выполняет
    как ПРЕДЛОЖЕНИЕ: сама функция обязана сохранить результат неподтверждённым
    (назначение — как предложение, показатель — как ожидающий проверки).
    """
    action = get(name)
    if action is None:
        raise ActionUnknown(name)
    if by == "assistant" and action.level == DOCTOR_ONLY:
        raise ActionDenied(action.why_doctor_only or
                           f"«{action.title}» делает только врач вручную")
    if action.run is None:
        raise ActionUnknown(f"{name}: действие объявлено, но не подключено")
    return action.run(by=by, **kwargs)


# ── Что ассистенту запрещено ────────────────────────────────────────────────
# Это не пожелание, а проверка: тест ниже следит, чтобы уровень не понизили
# по невнимательности.

register(Action(
    name="trigger.manage", level=DOCTOR_ONLY, title="Триггеры и автослежение",
    why_doctor_only="Правила слежения меняет только врач вручную — "
                    "в «Ещё → Автослежение». Ассистент их не трогает.",
))

register(Action(
    name="patient.create", level=DOCTOR_ONLY, title="Создание карты пациента",
    why_doctor_only="Карту заводит врач: при совпадении фамилий ассистент может "
                    "ошибиться тёзкой, а разделить потом смешанные истории нельзя.",
))

register(Action(
    name="medical.delete", level=DOCTOR_ONLY, title="Удаление медицинских данных",
    why_doctor_only="Удаление медицинских записей делает только врач.",
))
