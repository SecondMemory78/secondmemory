"""онбординг и списки: is_training, doctorprogress, reminder.parameter_code

Изменения схемы этой итерации (для уже существующих БД, накативших 0001;
на чистой БД baseline создаёт всё по моделям сразу).

Revision ID: 0002_onboarding_and_lists
Revises: 0001_baseline
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_onboarding_and_lists"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _has_column(bind, table, col) -> bool:
    insp = sa.inspect(bind)
    return col in [c["name"] for c in insp.get_columns(table)]


def _has_table(bind, table) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    # Patient.is_training — учебный пациент онбординга
    if not _has_column(bind, "patient", "is_training"):
        op.add_column("patient", sa.Column("is_training", sa.Boolean(),
                                           nullable=False, server_default=sa.false()))
        op.create_index("ix_patient_is_training", "patient", ["is_training"])

    # Reminder.parameter_code — что контролируем (для списка C01)
    if not _has_column(bind, "reminder", "parameter_code"):
        op.add_column("reminder", sa.Column("parameter_code", sa.String(),
                                            nullable=False, server_default=""))
        op.create_index("ix_reminder_parameter_code", "reminder", ["parameter_code"])

    # DoctorProgress — прогресс онбординга и увиденные подсказки
    if not _has_table(bind, "doctorprogress"):
        op.create_table(
            "doctorprogress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor.id"), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("seen_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_doctorprogress_doctor_id", "doctorprogress", ["doctor_id"])
        op.create_index("ix_doctorprogress_key", "doctorprogress", ["key"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "doctorprogress"):
        op.drop_table("doctorprogress")
    if _has_column(bind, "reminder", "parameter_code"):
        op.drop_index("ix_reminder_parameter_code", "reminder")
        op.drop_column("reminder", "parameter_code")
    if _has_column(bind, "patient", "is_training"):
        op.drop_index("ix_patient_is_training", "patient")
        op.drop_column("patient", "is_training")
