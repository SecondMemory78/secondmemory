"""Подключение к базе данных.

Для разработки — SQLite. На продакшене (РФ-хостинг, 152-ФЗ) заменяется на
PostgreSQL простым изменением DATABASE_URL, схема данных не меняется.
"""
import os
from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./second_memory.db")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def init_db() -> None:
    """Dev/тесты на SQLite — создаём таблицы автоматически.
    На Postgres схему ведёт Alembic (иначе новые колонки не добавятся →
    «no such column»); поэтому там create_all НЕ вызываем."""
    if DATABASE_URL.startswith("sqlite"):
        SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        # RLS-scope: врач видит только своих (второй слой к коду). No-op на SQLite.
        try:
            from .services.rls import set_session_scope
            from .deps import _doctor_id
            did = _doctor_id.get()
            # нет контекста врача (админ по x-admin-token или ещё не резолвнут) → bypass;
            # реальные запросы данных врача всегда имеют did (ставит middleware по токену)
            set_session_scope(session, did, bypass=(did is None))
        except Exception:
            pass
        yield session
