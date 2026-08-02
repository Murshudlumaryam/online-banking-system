"""Phase 7: add TOTP two-factor authentication columns to users

Revision ID: 0004_phase7_2fa
Revises: 0003_phase3_transactions
Create Date: 2026-07-16

"""
import sqlalchemy as sa

from alembic import op

revision = "0004_phase7_2fa"
down_revision = "0003_phase3_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
