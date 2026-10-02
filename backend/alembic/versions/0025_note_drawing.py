"""рисунок в заметке

Врачи рисуют пациенту схемы на бумажках, и бумажка теряется. Рисунок живёт
внутри заметки картинкой: текста в нём нет, искать по нему мы не будем — так
и задумано.

Revision ID: 0025_note_drawing
Revises: 0024_notes_blocknote
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_note_drawing"
down_revision = "0024_notes_blocknote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "doctornote" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("doctornote")}
    if "drawing" not in have:
        # PNG в виде строки data:. Отдельного хранилища файлов у нас нет, а
        # набросок весит десятки килобайт — заводить его ради этого рано.
        op.add_column("doctornote",
                      sa.Column("drawing", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "drawing" in {c["name"] for c in insp.get_columns("doctornote")}:
        op.drop_column("doctornote", "drawing")
