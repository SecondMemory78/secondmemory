"""личные заметки врача («Мои заметки», без привязки к пациенту)

Revision ID: 0011_doctor_notes
Revises: 0010_assistant_action
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_doctor_notes"
down_revision = "0010_assistant_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "doctornote" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "doctornote",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(), nullable=False, server_default="typed"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_doctornote_doctor_id", "doctornote", ["doctor_id"])


def downgrade() -> None:
    op.drop_index("ix_doctornote_doctor_id", table_name="doctornote")
    op.drop_table("doctornote")
