"""Add UNIQUE(transaction_id, entry_type) on ledger_entries

Defense-in-depth against the double-confirmation race condition fixed in
app/modules/transactions/service.py (TransactionRepository.get_for_update +
re-checking status under lock). Even if that application-level fix ever
regressed, the database itself now refuses a second DEBIT or CREDIT row for
the same transaction.

Revision ID: 0007_ledger_duplicate_protection
Revises: 0006_phase9_totp_encryption
Create Date: 2026-08-02

"""
from alembic import op

revision = "0007_ledger_duplicate_protection"
down_revision = "0006_phase9_totp_encryption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ledger_entries_transaction_entry_type",
        "ledger_entries",
        ["transaction_id", "entry_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ledger_entries_transaction_entry_type", "ledger_entries", type_="unique"
    )
