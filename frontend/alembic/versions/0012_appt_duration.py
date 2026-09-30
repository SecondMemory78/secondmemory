"""приём: длительность и время завершения

Revision ID: 0012_appt_duration
Revises: 0011_doctor_notes
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_appt_duration"
down_revision = "0011_doctor_notes"
branch_labels = None
depends_on = None


def _has(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has(bind, "appointment", "duration_min"):
        op.add_column("appointment", sa.Column("duration_min", sa.Integer(), nullable=False,
                                               server_default="20"))
    if not _has(bind, "appointment", "ended_at"):
        op.add_column("appointment", sa.Column("ended_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has(bind, "appointment", "ended_at"):
        op.drop_column("appointment", "ended_at")
    if _has(bind, "appointment", "duration_min"):
        op.drop_column("appointment", "duration_min")
