"""Пересоздать локальную БД разработки (dev).

Зачем: SQLModel.create_all() НЕ добавляет новые колонки в уже существующую
таблицу. После изменения моделей старый .db даёт «no such column: doctor.email».
В проде эту задачу решает Alembic (миграции); в dev проще пересоздать.

Запуск (сначала останови uvicorn, иначе файл занят):
    python -m app.reset_db
"""
import os
import glob


def main():
    removed = []
    url = os.getenv("DATABASE_URL", "")
    candidates = []
    if url.startswith("sqlite"):
        candidates.append(url.split("///")[-1])
    candidates += glob.glob("second_memory.db*")   # .db, .db-wal, .db-shm
    for f in set(candidates):
        if f and os.path.exists(f):
            try:
                os.remove(f); removed.append(f)
            except PermissionError:
                print(f"Не удалось удалить {f} — остановите uvicorn и повторите.")
                return

    from .db import init_db
    init_db()
    from . import seed
    seed.run()
    print("Готово. Удалено:", removed or "нечего было удалять",
          "· таблицы созданы по текущим моделям · демо-данные засеяны.")
    print("Демо-вход: doctor@demo.ru / demo12345 (или кнопка «Посмотреть демо»).")


if __name__ == "__main__":
    main()
