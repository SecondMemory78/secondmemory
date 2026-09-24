"""назначения: status + cancelled_at (для Q02b/Q06)

Revision ID: 0004_prescription_status
Revises: 0003_devices
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_prescription_status"
down_revision = "0003_devices"
branch_labels = None
depends_on = None


def _has_column(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "prescription", "status"):
        op.add_column("prescription", sa.Column("status", sa.String(), nullable=False,
                                                server_default="active"))
        op.create_index("ix_prescription_status", "prescription", ["status"])
    if not _has_column(bind, "prescription", "cancelled_at"):
        op.add_column("prescription", sa.Column("cancelled_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "prescription", "cancelled_at"):
        op.drop_column("prescription", "cancelled_at")
    if _has_column(bind, "prescription", "status"):
        op.drop_index("ix_prescription_status", "prescription")
        op.drop_column("prescription", "status")
