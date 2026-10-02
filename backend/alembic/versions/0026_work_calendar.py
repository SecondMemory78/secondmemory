"""производственный календарь: праздники и переносы

Выходные вычисляются из даты, а праздники в России каждый год утверждаются
постановлением правительства — переносы меняются, вычислить их нельзя. Значит
даты вносит человек, и хранить их надо в базе, чтобы обновление не требовало
выкладки новой версии приложения.

Revision ID: 0026_work_calendar
Revises: 0025_note_drawing
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_work_calendar"
down_revision = "0025_note_drawing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "workcalendarday" in insp.get_table_names():
        return
    op.create_table(
        "workcalendarday",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        # unique объявляем ПРЯМО в таблице. Отдельным вызовом нельзя: SQLite не
        # поддерживает ALTER для ограничений, и на чистой базе миграция падала
        # с NotImplementedError. У меня она прошла только потому, что таблица
        # уже существовала и функция выходила раньше — проверка была пустой.
        sa.Column("day", sa.Date(), nullable=False, index=True, unique=True),
        # holiday — нерабочий праздничный; short — сокращённый предпраздничный;
        # working — рабочая суббота/воскресенье (перенос)
        sa.Column("kind", sa.String(), nullable=False, server_default="holiday"),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "workcalendarday" in insp.get_table_names():
        op.drop_table("workcalendarday")
