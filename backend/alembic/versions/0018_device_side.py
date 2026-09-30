"""устройства: сторона, локализация, размер и показание

Сторона для урологии существенна: «стент справа» и «стент слева» — разные
устройства и разные действия. Раньше это можно было записать только текстом
в метку, и в памятку/выписку сторона попадала как придётся.

Revision ID: 0018_device_side
Revises: 0017_source_lookup
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_device_side"
down_revision = "0017_source_lookup"
branch_labels = None
depends_on = None

_COLUMNS = {
    "side": sa.Column("side", sa.String(), nullable=False, server_default=""),
    "location": sa.Column("location", sa.String(), nullable=False, server_default=""),
    "size": sa.Column("size", sa.String(), nullable=False, server_default=""),
    "indication": sa.Column("indication", sa.String(), nullable=False, server_default=""),
    "state": sa.Column("state", sa.String(), nullable=False, server_default="active"),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "device" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("device")}
    for name, col in _COLUMNS.items():
        if name not in have:
            op.add_column("device", col)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("device")}
    for name in _COLUMNS:
        if name in have:
            op.drop_column("device", name)
