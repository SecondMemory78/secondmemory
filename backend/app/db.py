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


class AppSession(Session):
    """Сессия, которая не «протухает» после commit.

    По умолчанию SQLAlchemy после commit помечает все объекты устаревшими, и
    следующее же обращение к любому полю лезет в базу заново. Это ловушка,
    которая в проекте срабатывала уже четыре раза (заметки, приёмы, показатели,
    поддержка): после commit читаем t.id — и получаем либо пустой ответ, либо
    ObjectDeletedError, если повторный запрос ничего не вернул.

    Нам обновление после commit не нужно: запрос короткий, данные в нём свои.
    Поэтому expire_on_commit выключен для всех сессий приложения разом.
    """

    def __init__(self, bind=None, scope_doctor_id="auto", **kw):
        kw.setdefault("expire_on_commit", False)
        super().__init__(bind if bind is not None else engine, **kw)
        self._scope_doctor_id = scope_doctor_id

    def __enter__(self):
        """Выставляет контекст изоляции строк на подключении.

        Зачем это здесь, а не в вызывающем коде. Подключения берутся из пула, и
        параметр app.current_doctor_id остаётся на подключении от прошлого
        запроса. Сессия, открытая без контекста, читала данные под ЧУЖИМ врачом —
        отсюда ложный 402 у оплатившего врача: барьер подписки не видел его
        подписку, потому что искал её под чужим контекстом. Непостоянно,
        проходило после перезапуска (пул свежий) и только на PostgreSQL.

        Делаем это в самой сессии, а не в каждом из двенадцати мест, где она
        открывается: место, которое забыли, — это и есть такая ошибка.
        """
        out = super().__enter__()
        try:
            from .services.rls import set_session_scope
            did = self._scope_doctor_id
            if did == "auto":
                from .deps import _doctor_id
                did = _doctor_id.get()
            # Нет врача в контексте — фоновая задача: ей нужны все врачи.
            set_session_scope(out, did, bypass=(did is None))
        except Exception:
            pass
        return out


def init_db() -> None:
    """Dev/тесты на SQLite — создаём таблицы автоматически.
    На Postgres схему ведёт Alembic (иначе новые колонки не добавятся →
    «no such column»); поэтому там create_all НЕ вызываем."""
    if DATABASE_URL.startswith("sqlite"):
        SQLModel.metadata.create_all(engine)


def get_session():
    with AppSession() as session:
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
