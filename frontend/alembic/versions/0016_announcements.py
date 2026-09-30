"""объявления врачам из админки (техработы, важное, новости)

Revision ID: 0016_announcements
Revises: 0015_prescription_full
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_announcements"
down_revision = "0015_prescription_full"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "announcement" not in tables:
        op.create_table(
            "announcement",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(), nullable=False, server_default="maintenance"),
            sa.Column("title", sa.String(), nullable=False, server_default=""),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.Column("dismissible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("audience", sa.String(), nullable=False, server_default="all"),
            sa.Column("doctor_ids", sa.Text(), nullable=False, server_default=""),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=False, server_default=""),
        )
        op.create_index("ix_announcement_active", "announcement", ["active"])
        op.create_index("ix_announcement_kind", "announcement", ["kind"])

    if "announcementread" not in tables:
        op.create_table(
            "announcementread",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("announcement_id", sa.Integer(),
                      sa.ForeignKey("announcement.id"), nullable=False),
            sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
            sa.Column("dismissed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_annread_doctor", "announcementread", ["doctor_id"])
        op.create_index("ix_annread_ann", "announcementread", ["announcement_id"])


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "announcementread" in tables:
        op.drop_table("announcementread")
    if "announcement" in tables:
        op.drop_table("announcement")
