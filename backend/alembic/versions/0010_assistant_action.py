"""журнал действий ИИ-ассистента (для врача)

Revision ID: 0010_assistant_action
Revises: 0009_consent_signature
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_assistant_action"
down_revision = "0009_consent_signature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "assistantaction" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "assistantaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("channel", sa.String(), nullable=False, server_default="text"),
        sa.Column("area", sa.String(), nullable=False, server_default=""),
        sa.Column("intent", sa.String(), nullable=False, server_default=""),
        sa.Column("input_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(), nullable=False, server_default=""),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assistantaction_doctor_id", "assistantaction", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_assistantaction_doctor_id", table_name="assistantaction")
    op.drop_table("assistantaction")
