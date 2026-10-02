"""операции и процедуры

Их не было как сущности вовсе. Без них нельзя ни собрать выписку (там
отдельный раздел «операции»), ни ответить на вопрос «какая последняя операция
у пациента» — он был в ТЗ и до сих пор отвечался отказом.

Revision ID: 0022_procedures
Revises: 0021_diagnosis_confirm
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_procedures"
down_revision = "0021_diagnosis_confirm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "procedure" in insp.get_table_names():
        return
    op.create_table(
        "procedure",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), index=True, nullable=False),
        sa.Column("encounter_id", sa.Integer(), sa.ForeignKey("encounter.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("code", sa.String(), nullable=False, server_default=""),
        sa.Column("performed_at", sa.Date(), nullable=True),
        # Сторона для урологии существенна ровно как у устройств.
        sa.Column("side", sa.String(), nullable=False, server_default=""),
        sa.Column("location", sa.String(), nullable=False, server_default=""),
        sa.Column("anesthesia", sa.String(), nullable=False, server_default=""),
        sa.Column("surgeon", sa.String(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(), nullable=False, server_default=""),
        sa.Column("complications", sa.String(), nullable=False, server_default=""),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        # Устройство, установленное в ходе операции: ТЗ требует связи.
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("device.id"), nullable=True),
        # Как и у диагноза: предложенное ассистентом ждёт врача.
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(), nullable=False, server_default="doctor"),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="done"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "procedure" in insp.get_table_names():
        op.drop_table("procedure")
