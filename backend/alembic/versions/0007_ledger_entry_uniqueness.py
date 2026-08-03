"""Add ledger entry duplicate protection

Revision ID: 0007_ledger_entry_uniqueness
Revises: 0006_phase9_totp_encryption
Create Date: 2026-08-02

"""
from alembic import op

revision = "0007_ledger_entry_uniqueness"
down_revision = "0006_phase9_totp_encryption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ledger_entries_transaction_account_type",
        "ledger_entries",
        ["transaction_id", "account_id", "entry_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ledger_entries_transaction_account_type",
        "ledger_entries",
        type_="unique",
    )
