"""baseline — все таблицы по текущим моделям

Проект начинал с create_all; эта базовая ревизия фиксирует текущую схему.
Дальнейшие изменения моделей → `alembic revision --autogenerate -m "..."`.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-01
"""
from alembic import op
from sqlmodel import SQLModel
import app.models  # noqa: F401 — заполняет метаданные

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind())
