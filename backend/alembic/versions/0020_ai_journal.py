"""журнал ИИ: чем разобрано, какой моделью, что подтвердил врач

ТЗ требует, чтобы в логе ИИ были исходный источник, результат извлечения,
версия модели или правила и последующее подтверждение либо исправление. Раньше
журнал писал только намерение и текст команды: ответить на вопрос «почему в
карте оказалось это значение» по нему было нельзя.

Revision ID: 0020_ai_journal
Revises: 0019_fact_provenance
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_ai_journal"
down_revision = "0019_fact_provenance"
branch_labels = None
depends_on = None

_COLUMNS = {
    # rules | model | mixed — чем разобрана команда
    "engine": sa.Column("engine", sa.String(), nullable=False, server_default="rules"),
    # версия модели или правил, которая сработала
    "engine_version": sa.Column("engine_version", sa.String(), nullable=False, server_default=""),
    # что врач сделал потом: confirmed | edited | rejected | "" (ещё ничего)
    "outcome": sa.Column("outcome", sa.String(), nullable=False, server_default=""),
    "outcome_at": sa.Column("outcome_at", sa.DateTime(), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "assistantaction" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("assistantaction")}
    for name, col in _COLUMNS.items():
        if name not in have:
            op.add_column("assistantaction", col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("assistantaction")}
    for name in _COLUMNS:
        if name in have:
            op.drop_column("assistantaction", name)
