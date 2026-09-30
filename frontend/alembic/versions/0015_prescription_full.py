"""назначения: универсальная структура + история изменений

Revision ID: 0015_prescription_full
Revises: 0014_note_soft_delete
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_prescription_full"
down_revision = "0014_note_soft_delete"
branch_labels = None
depends_on = None

_COLS = [
    ("category", sa.String(), "drug"),
    ("indication", sa.Text(), ""),
    ("instruction", sa.Text(), ""),
    ("route", sa.String(), ""),
    ("frequency", sa.String(), ""),
    ("duration", sa.String(), ""),
    ("control", sa.Text(), ""),
    ("source", sa.String(), "doctor"),
    ("priority", sa.String(), "normal"),
    ("cancel_reason", sa.Text(), ""),
    ("effect", sa.String(), ""),
]


def _cols(bind, table):
    return [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    have = _cols(bind, "prescription")
    for name, type_, default in _COLS:
        if name not in have:
            op.add_column("prescription", sa.Column(name, type_, nullable=False,
                                                    server_default=default))
    if "starts_on" not in have:
        op.add_column("prescription", sa.Column("starts_on", sa.Date(), nullable=True))
    if "control_date" not in have:
        op.add_column("prescription", sa.Column("control_date", sa.Date(), nullable=True))
    if "confirmed" not in have:
        op.add_column("prescription", sa.Column("confirmed", sa.Boolean(), nullable=False,
                                                server_default=sa.true()))
    if "updated_at" not in have:
        op.add_column("prescription", sa.Column("updated_at", sa.DateTime(), nullable=True))

    if "prescriptionrevision" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "prescriptionrevision",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prescription_id", sa.Integer(),
                      sa.ForeignKey("prescription.id"), nullable=False),
            sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("snapshot", sa.Text(), nullable=False, server_default=""),
        )
        op.create_index("ix_presrev_prescription", "prescriptionrevision", ["prescription_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "prescriptionrevision" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_presrev_prescription", table_name="prescriptionrevision")
        op.drop_table("prescriptionrevision")
    have = _cols(bind, "prescription")
    for name in ([c[0] for c in _COLS]
                 + ["starts_on", "control_date", "confirmed", "updated_at"]):
        if name in have:
            op.drop_column("prescription", name)
