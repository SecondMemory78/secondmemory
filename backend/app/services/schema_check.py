"""Проверка, что база не отстала от кода.

Зачем. Приложение само создаёт недостающие ТАБЛИЦЫ, но не КОЛОНКИ: их
добавляет только `alembic upgrade head`. Поэтому забытая миграция выглядит не
как внятная ошибка при запуске, а как случайный «no such column» через полчаса
работы — врач видит красную плашку и не понимает, что произошло.

За одну сессию на это наступили трижды: дважды Mickl и один раз я сам при
проверке. Ошибка не в невнимательности, а в том, что приложение об этом молчит.

Запуск мы НЕ блокируем: на сервере это означало бы уронить работающее
приложение из-за одной забытой миграции. Но не заметить теперь нельзя.
"""
from __future__ import annotations


def pending_migrations(engine) -> list[str]:
    """Какие миграции не применены. Пустой список — база в порядке."""
    from pathlib import Path
    import re

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "alembic_version" not in insp.get_table_names():
        return []                       # база ещё ни разу не мигрировала

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    current = {r[0] for r in rows}
    if not current:
        return []

    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    if not versions_dir.exists():
        return []

    # Строим цепочку: revision → down_revision
    revs: dict[str, str | None] = {}
    for f in versions_dir.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)', src, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']?([^"\'\n]+)', src, re.M)
        if m:
            down = (d.group(1).strip() if d else None)
            revs[m.group(1)] = None if down in (None, "None") else down

    if not revs:
        return []

    # Голова цепочки — та ревизия, на которую никто не ссылается как на down
    downs = {v for v in revs.values() if v}
    heads = [r for r in revs if r not in downs]

    # Идём от головы вниз, собирая всё, чего нет в базе
    pending: list[str] = []
    for head in heads:
        node = head
        while node and node not in current:
            pending.append(node)
            node = revs.get(node)
    return list(reversed(pending))


def warn_if_outdated(engine) -> str:
    """Пишет в журнал понятное предупреждение. Возвращает текст (или пусто)."""
    try:
        pending = pending_migrations(engine)
    except Exception:
        return ""                       # проверка не должна мешать запуску
    if not pending:
        return ""

    msg = (
        "\n" + "=" * 70 +
        "\nБАЗА ДАННЫХ ОТСТАЛА ОТ КОДА."
        f"\nНе применены миграции ({len(pending)}): " + ", ".join(pending) +
        "\n\nПриложение запущено, но часть экранов будет отвечать ошибкой"
        "\n«no such column» — колонки в базе ещё нет."
        "\n\nВыполните:  alembic upgrade head"
        "\n" + "=" * 70 + "\n"
    )
    print(msg, flush=True)
    return msg
