"""документ: находки из заключения

Находки — не показатели: у них есть орган, сторона и свойства, и в динамику
они не идут. Хранятся рядом с текстом документа.

Revision ID: 0028_doc_findings
Revises: 0027_doc_rejected
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_doc_findings"
down_revision = "0027_doc_rejected"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "sourcedocument" not in insp.get_table_names():
        return
    if "findings_json" not in {c["name"] for c in insp.get_columns("sourcedocument")}:
        op.add_column("sourcedocument",
                      sa.Column("findings_json", sa.Text(), nullable=False,
                                server_default="[]"))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "findings_json" in {c["name"] for c in insp.get_columns("sourcedocument")}:
        op.drop_column("sourcedocument", "findings_json")
