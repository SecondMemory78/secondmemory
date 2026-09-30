"""показатели: происхождение факта и подтверждение врачом

ТЗ требует различать три разных вопроса, которые раньше были слиты в одно
поле status: откуда взялось значение, насколько уверена модель и подтвердил ли
его врач. Отдельно — кто и когда подтвердил: по одному слову «confirmed» на
вопрос «кто это внёс и на основании чего» не ответить.

Revision ID: 0019_fact_provenance
Revises: 0018_device_side
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_fact_provenance"
down_revision = "0018_device_side"
branch_labels = None
depends_on = None

_COLUMNS = {
    # doctor | document | patient_words | ai_extracted | import
    "provenance": sa.Column("provenance", sa.String(), nullable=False, server_default="doctor"),
    "machine_extracted": sa.Column("machine_extracted", sa.Boolean(), nullable=False,
                                   server_default=sa.false()),
    "confidence": sa.Column("confidence", sa.Float(), nullable=True),
    "confirmed_by": sa.Column("confirmed_by", sa.Integer(), nullable=True),
    "confirmed_at": sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    "for_handout": sa.Column("for_handout", sa.Boolean(), nullable=False,
                             server_default=sa.false()),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "observation" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("observation")}
    for name, col in _COLUMNS.items():
        if name not in have:
            op.add_column("observation", col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("observation")}
    for name in _COLUMNS:
        if name in have:
            op.drop_column("observation", name)
