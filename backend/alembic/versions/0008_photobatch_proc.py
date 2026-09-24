"""фото-конвейер: proc_status + proc_error на photobatch

Revision ID: 0008_photobatch_proc
Revises: 0007_backup_codes
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_photobatch_proc"
down_revision = "0007_backup_codes"
branch_labels = None
depends_on = None


def _has_column(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "photobatch", "proc_status"):
        op.add_column("photobatch", sa.Column("proc_status", sa.String(), nullable=False,
                                              server_default="done"))
        op.create_index("ix_photobatch_proc_status", "photobatch", ["proc_status"])
    if not _has_column(bind, "photobatch", "proc_error"):
        op.add_column("photobatch", sa.Column("proc_error", sa.String(), nullable=False,
                                              server_default=""))
    if not _has_column(bind, "photobatch", "sim_json"):
        op.add_column("photobatch", sa.Column("sim_json", sa.String(), nullable=False,
                                              server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "photobatch", "proc_error"):
        op.drop_column("photobatch", "proc_error")
    if _has_column(bind, "photobatch", "proc_status"):
        op.drop_index("ix_photobatch_proc_status", "photobatch")
        op.drop_column("photobatch", "proc_status")
