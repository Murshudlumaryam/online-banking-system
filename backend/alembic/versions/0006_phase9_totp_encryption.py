"""Phase 9: widen users.totp_secret for encrypted (Fernet) storage

Revision ID: 0006_phase9_totp_encryption
Revises: 0005_phase7_scheduled_payments
Create Date: 2026-07-29

"""
import sqlalchemy as sa

from alembic import op

revision = "0006_phase9_totp_encryption"
down_revision = "0005_phase7_scheduled_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A raw base32 TOTP secret is ~32 chars; a Fernet-encrypted token of one
    # is ~140. Existing plaintext secrets (from before this migration) still
    # fit in the wider column as-is, but are NOT automatically re-encrypted —
    # see the data-migration note in backend/README.md's Phase 9 section.
    # In practice this only matters for a deployment that had real users
    # enroll in 2FA before this migration ran; a fresh deployment has none.
    op.alter_column(
        "users",
        "totp_secret",
        type_=sa.String(255),
        existing_type=sa.String(64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        type_=sa.String(64),
        existing_type=sa.String(255),
        existing_nullable=True,
    )
