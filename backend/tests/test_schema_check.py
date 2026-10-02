"""Проверка, что база не отстала от кода.

Приложение само создаёт недостающие ТАБЛИЦЫ, но не КОЛОНКИ — их добавляет
только alembic. Поэтому забытая миграция выглядела не как внятная ошибка при
запуске, а как случайный «no such column» через полчаса работы.

За одну сессию на это наступили трижды. Ошибка не в невнимательности:
приложение об этом молчало.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from sqlalchemy import create_engine
from app.services.schema_check import pending_migrations, warn_if_outdated

BACKEND = Path(__file__).resolve().parents[1]


def _db_at(revision: str) -> str:
    """Поднимает базу на заданной ревизии и возвращает путь."""
    path = tempfile.mktemp(suffix=".db")
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{path}")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
                   cwd=BACKEND, env=env, capture_output=True, check=True)
    return path


def test_актуальная_база_не_ругается():
    eng = create_engine(f"sqlite:///{_db_at('head')}")
    assert pending_migrations(eng) == []
    assert warn_if_outdated(eng) == ""


def test_отставшая_база_называет_миграции():
    eng = create_engine(f"sqlite:///{_db_at('0024_notes_blocknote')}")
    pending = pending_migrations(eng)
    assert pending, "отставание не замечено"
    assert "0027_doc_rejected" in pending
    # порядок от старых к новым — так их и применять
    assert pending[0] == "0025_note_drawing"


def test_предупреждение_говорит_что_делать():
    eng = create_engine(f"sqlite:///{_db_at('0024_notes_blocknote')}")
    msg = warn_if_outdated(eng)
    assert "alembic upgrade head" in msg
    assert "no such column" in msg      # врач увидит именно эту ошибку


def test_проверка_не_падает_на_пустой_базе():
    """Первый запуск вообще без миграций не должен ломать старт."""
    eng = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}")
    assert pending_migrations(eng) == []


def test_запуск_не_блокируется():
    """На сервере блокировка уронила бы работающее приложение."""
    eng = create_engine(f"sqlite:///{_db_at('0024_notes_blocknote')}")
    warn_if_outdated(eng)               # просто не должно бросить исключение
