"""согласие: подпись (ПЭП) + версия соглашения о простой ЭП

Revision ID: 0009_consent_signature
Revises: 0008_photobatch_proc
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_consent_signature"
down_revision = "0008_photobatch_proc"
branch_labels = None
depends_on = None


def _has_column(bind, table, col) -> bool:
    return col in [c["name"] for c in sa.inspect(bind).get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "patientconsent", "signature"):
        op.add_column("patientconsent", sa.Column("signature", sa.Text(), nullable=False,
                                                   server_default=""))
    if not _has_column(bind, "patientconsent", "es_agreement_version"):
        op.add_column("patientconsent", sa.Column("es_agreement_version", sa.String(),
                                                   nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "patientconsent", "es_agreement_version"):
        op.drop_column("patientconsent", "es_agreement_version")
    if _has_column(bind, "patientconsent", "signature"):
        op.drop_column("patientconsent", "signature")
