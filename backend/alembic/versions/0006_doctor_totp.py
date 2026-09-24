"""врач: totp_secret + totp_enabled (2FA через приложение-аутентификатор)

Revision ID: 0006_doctor_totp
Revises: 0005_subscription_payment_unique
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_doctor_totp"
down_revision = "0005_subscription_payment_unique"
branch_labels = None
depends_on = None


def _has_column(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "doctor", "totp_secret"):
        op.add_column("doctor", sa.Column("totp_secret", sa.Text(), nullable=False,
                                          server_default=""))
    if not _has_column(bind, "doctor", "totp_enabled"):
        op.add_column("doctor", sa.Column("totp_enabled", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "doctor", "totp_enabled"):
        op.drop_column("doctor", "totp_enabled")
    if _has_column(bind, "doctor", "totp_secret"):
        op.drop_column("doctor", "totp_secret")
