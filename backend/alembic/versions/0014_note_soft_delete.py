"""заметки врача: мягкое удаление (для «Отменить»)

Revision ID: 0014_note_soft_delete
Revises: 0013_appt_reschedule
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_note_soft_delete"
down_revision = "0013_appt_reschedule"
branch_labels = None
depends_on = None


def _has(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has(bind, "doctornote", "deleted_at"):
        op.add_column("doctornote", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has(bind, "doctornote", "deleted_at"):
        op.drop_column("doctornote", "deleted_at")
