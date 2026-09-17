"""Ограничитель частоты попыток (анти-брутфорс).

In-memory: подходит для одного инстанса. Для нескольких воркеров/серверов
заменить хранилище на Redis (интерфейс check/reset тот же).
"""
import time

_hits: dict[str, list[float]] = {}


def check(key: str, max_attempts: int, window: int) -> tuple[bool, int]:
    """Регистрирует попытку. Возвращает (разрешено, сколько_секунд_ждать)."""
    now = time.time()
    arr = [t for t in _hits.get(key, []) if now - t < window]
    arr.append(now)
    _hits[key] = arr
    if len(arr) > max_attempts:
        return False, max(1, int(window - (now - arr[0])))
    return True, 0


def reset(key: str) -> None:
    _hits.pop(key, None)
