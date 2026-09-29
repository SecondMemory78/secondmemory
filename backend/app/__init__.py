"""Пакет приложения.

Единственное, что должно случиться ДО импорта остальных модулей, — загрузка
.env. Настройки (AI_PROVIDER, ключи, DATABASE_URL) читаются через os.getenv на
уровне модулей, то есть в момент импорта: загрузить файл позже — всё равно что
не загружать.

Ищем файл в нескольких местах и терпим типичные ошибки Windows: Блокнот
сохраняет «.env» как «.env.txt» (расширения скрыты — этого не видно) и
добавляет в начало файла невидимый BOM, из-за которого первая строка
перестаёт читаться.
"""
import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# Порядок важен: backend/.env — штатное место, остальное — подстраховка.
ENV_CANDIDATES = [
    _BACKEND_DIR / ".env",
    _BACKEND_DIR / ".env.txt",        # Блокнот дописал расширение
    _ROOT_DIR / ".env",               # положили в корень проекта
    _ROOT_DIR / ".env.txt",
    Path.cwd() / ".env",              # запуск из другой папки
]

LOADED_ENV_PATH: str | None = None    # какой файл реально подхватили (для диагностики)


def _parse_into_environ(path: Path) -> bool:
    """KEY=VALUE построчно. utf-8-sig снимает BOM. Реальное окружение важнее файла."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception:
        return False
    applied = False
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):        # формат из bash-примеров
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
        applied = True
    return applied


def _load_env_file(path: Path) -> bool:
    """Загрузить один файл. True — файл существует и разобран."""
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv               # необязательная зависимость
        load_dotenv(path, override=False, encoding="utf-8-sig")
        # python-dotenv молчит о результате — дочитываем сами, это идемпотентно
        _parse_into_environ(path)
        return True
    except Exception:
        return _parse_into_environ(path)


def _load_env() -> None:
    global LOADED_ENV_PATH
    for candidate in ENV_CANDIDATES:
        try:
            if _load_env_file(candidate):
                LOADED_ENV_PATH = str(candidate)
                return
        except Exception:
            continue                                  # битый файл не роняет запуск


_load_env()
