"""заметки: заголовок, папка, чек-лист, закрепление

«Блокнот» — заметки с элементами задач. Без заголовка список через месяц
превращается в стену текста, без папок — в свалку, а чек-лист нужен потому,
что мысль «заказать, спросить, позвонить» рождается в заметке, а не в списке
дел.

Revision ID: 0024_notes_blocknote
Revises: 0023_discharge
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_notes_blocknote"
down_revision = "0023_discharge"
branch_labels = None
depends_on = None

_COLUMNS = {
    "title": sa.Column("title", sa.String(), nullable=False, server_default=""),
    "folder": sa.Column("folder", sa.String(), nullable=False, server_default=""),
    # Чек-лист: JSON [{text, done, reminder_id}]. Отдельной таблицей делать
    # незачем — пункты живут только внутри своей заметки.
    "checklist": sa.Column("checklist", sa.Text(), nullable=False, server_default="[]"),
    # Пациент, которому заметку перенесли. Пусто — личная заметка врача.
    "patient_id": sa.Column("patient_id", sa.Integer(), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "doctornote" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("doctornote")}
    for name, col in _COLUMNS.items():
        if name not in have:
            op.add_column("doctornote", col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("doctornote")}
    for name in _COLUMNS:
        if name in have:
            op.drop_column("doctornote", name)
