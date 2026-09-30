"""кеш поиска по доверенным источникам

Revision ID: 0017_source_lookup
Revises: 0016_announcements
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_source_lookup"
down_revision = "0016_announcements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "sourcelookup" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "sourcelookup",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("quote", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_code", sa.String(), nullable=False, server_default=""),
        sa.Column("source_title", sa.String(), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope", sa.String(), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_sourcelookup_query", "sourcelookup", ["query"])
    op.create_index("ix_sourcelookup_status", "sourcelookup", ["status"])


def downgrade() -> None:
    op.drop_table("sourcelookup")
