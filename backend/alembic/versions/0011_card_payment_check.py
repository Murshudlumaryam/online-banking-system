"""Extend accounts-match-type CHECK constraint to cover CARD_PAYMENT

Must be a separate migration from 0010 — see that file's docstring for why
(Postgres/asyncpg won't allow a brand-new enum value to be referenced in
the same transaction that added it).

Revision ID: 0011_card_payment_check_constraint
Revises: 0010_card_delete_and_payment_type
Create Date: 2026-08-16

"""
from alembic import op

revision = "0011_card_payment_check"
down_revision = "0010_card_delete_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_transactions_accounts_match_type", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transactions_accounts_match_type",
        "transactions",
        "(transaction_type = 'TRANSFER' AND sender_account_id IS NOT NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'DEPOSIT' AND sender_account_id IS NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'WITHDRAWAL' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)"
        " OR (transaction_type = 'CARD_PAYMENT' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_transactions_accounts_match_type", "transactions", type_="check")
    op.create_check_constraint(
        "ck_transactions_accounts_match_type",
        "transactions",
        "(transaction_type = 'TRANSFER' AND sender_account_id IS NOT NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'DEPOSIT' AND sender_account_id IS NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'WITHDRAWAL' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)",
    )
