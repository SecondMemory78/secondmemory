"""резервные коды 2FA: таблица backupcode

Revision ID: 0007_backup_codes
Revises: 0006_doctor_totp
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_backup_codes"
down_revision = "0006_doctor_totp"
branch_labels = None
depends_on = None


def _has_table(bind, table) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "backupcode"):
        return
    op.create_table(
        "backupcode",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_backupcode_doctor_id", "backupcode", ["doctor_id"])
    op.create_index("ix_backupcode_code_hash", "backupcode", ["code_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "backupcode"):
        op.drop_table("backupcode")
