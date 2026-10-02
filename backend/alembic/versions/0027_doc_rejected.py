"""документ: что не прошло проверку и почему

Отклонённые значения не должны исчезать молча. Врач подписывает документы
своим именем и должен видеть, что система отбросила и по какой причине —
иначе он не узнает о пропуске.

Revision ID: 0027_doc_rejected
Revises: 0026_work_calendar
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_doc_rejected"
down_revision = "0026_work_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "sourcedocument" not in insp.get_table_names():
        return
    if "rejected_json" not in {c["name"] for c in insp.get_columns("sourcedocument")}:
        op.add_column("sourcedocument",
                      sa.Column("rejected_json", sa.Text(), nullable=False,
                                server_default="[]"))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "rejected_json" in {c["name"] for c in insp.get_columns("sourcedocument")}:
        op.drop_column("sourcedocument", "rejected_json")
