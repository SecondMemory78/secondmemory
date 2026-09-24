"""подписки: уникальный индекс payment_id (защита от гонки двойной активации)

Частичный уникальный индекс — только для непустых payment_id (пустые остаются
у dev/ручных активаций и не должны конфликтовать между собой).

Revision ID: 0005_subscription_payment_unique
Revises: 0004_prescription_status
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_subscription_payment_unique"
down_revision = "0004_prescription_status"
branch_labels = None
depends_on = None


def _has_index(bind, table, name) -> bool:
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_index(bind, "subscription", "uq_subscription_payment_id"):
        # partial unique — работает и в SQLite, и в PostgreSQL
        op.create_index("uq_subscription_payment_id", "subscription", ["payment_id"],
                        unique=True, sqlite_where=sa.text("payment_id != ''"),
                        postgresql_where=sa.text("payment_id != ''"))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "subscription", "uq_subscription_payment_id"):
        op.drop_index("uq_subscription_payment_id", "subscription")
