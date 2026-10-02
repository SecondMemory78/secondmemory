"""выписка по эпизоду: черновик, версии, финализация

Выписка — не документ, а рабочий процесс: черновик собирается из данных,
врач правит текст, и только подписанная версия становится неизменяемой.
Снимок исходных данных хранится вместе с версией: иначе через год нельзя
будет объяснить, почему в выписке именно эти цифры.

Revision ID: 0023_discharge
Revises: 0022_procedures
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_discharge"
down_revision = "0022_procedures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "discharge" in insp.get_table_names():
        return
    op.create_table(
        "discharge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), index=True, nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient.id"), index=True, nullable=False),
        sa.Column("encounter_id", sa.Integer(), sa.ForeignKey("encounter.id"), index=True, nullable=False),
        # draft — собирается и правится; final — подписана и больше не меняется
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Разделы документа как их видит врач (JSON): правки врача живут здесь.
        sa.Column("sections", sa.Text(), nullable=False, server_default="{}"),
        # Что НЕ вошло и почему — показывается врачу, в документ не попадает.
        sa.Column("excluded", sa.Text(), nullable=False, server_default="[]"),
        # Снимок исходных данных на момент сборки: чем объяснять цифры потом.
        sa.Column("source_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("finalized_by", sa.Integer(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "discharge" in insp.get_table_names():
        op.drop_table("discharge")
