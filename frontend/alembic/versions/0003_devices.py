"""устройства (C02): таблица device

Revision ID: 0003_devices
Revises: 0002_onboarding_and_lists
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_devices"
down_revision = "0002_onboarding_and_lists"
branch_labels = None
depends_on = None


def _has_table(bind, table) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "device"):
        return
    op.create_table(
        "device",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("installed_at", sa.Date(), nullable=True),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.Date(), nullable=True),
        sa.Column("closed_action", sa.String(), nullable=False, server_default=""),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_device_doctor_id", "device", ["doctor_id"])
    op.create_index("ix_device_patient_id", "device", ["patient_id"])
    op.create_index("ix_device_kind", "device", ["kind"])
    op.create_index("ix_device_active", "device", ["active"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "device"):
        op.drop_table("device")
