"""диагноз: подтверждение врачом и источник

Диагноз — клиническое суждение, и ошибка в нём весит не меньше, чем в
назначении. Назначение от ассистента давно создаётся предложением, а диагноз
попадал в карту сразу. Выравниваем.

Существующие диагнозы помечаются подтверждёнными: их вносил врач руками.

Revision ID: 0021_diagnosis_confirm
Revises: 0020_ai_journal
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_diagnosis_confirm"
down_revision = "0020_ai_journal"
branch_labels = None
depends_on = None

_COLUMNS = {
    # Для уже существующих записей — true: их вносил врач.
    "confirmed": sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
    "source": sa.Column("source", sa.String(), nullable=False, server_default="doctor"),
    "confirmed_by": sa.Column("confirmed_by", sa.Integer(), nullable=True),
    "confirmed_at": sa.Column("confirmed_at", sa.DateTime(), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "patientdiagnosis" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("patientdiagnosis")}
    for name, col in _COLUMNS.items():
        if name not in have:
            op.add_column("patientdiagnosis", col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("patientdiagnosis")}
    for name in _COLUMNS:
        if name in have:
            op.drop_column("patientdiagnosis", name)
