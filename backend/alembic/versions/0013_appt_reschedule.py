"""приём: история переноса (откуда перенесли и сколько раз)

Revision ID: 0013_appt_reschedule
Revises: 0012_appt_duration
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_appt_reschedule"
down_revision = "0012_appt_duration"
branch_labels = None
depends_on = None


def _has(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has(bind, "appointment", "rescheduled_from"):
        op.add_column("appointment", sa.Column("rescheduled_from", sa.DateTime(), nullable=True))
    if not _has(bind, "appointment", "reschedule_count"):
        op.add_column("appointment", sa.Column("reschedule_count", sa.Integer(),
                                               nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    if _has(bind, "appointment", "reschedule_count"):
        op.drop_column("appointment", "reschedule_count")
    if _has(bind, "appointment", "rescheduled_from"):
        op.drop_column("appointment", "rescheduled_from")
