"""Add deposit/withdrawal support to transactions

- transactions.transaction_type (TRANSFER/DEPOSIT/WITHDRAWAL), default
  TRANSFER for all existing rows
- sender_account_id / receiver_account_id become nullable (a DEPOSIT has no
  sender, a WITHDRAWAL has no receiver — money crossing this closed-loop
  system's boundary rather than moving between two of its own accounts)
- transactions.note (free-text operational note) and
  transactions.performed_by_user_id (which admin initiated a
  deposit/withdrawal; NULL for an ordinary customer transfer)
- a CHECK constraint tying sender/receiver nullability to transaction_type

Revision ID: 0008_deposit_withdrawal
Revises: 0007_ledger_duplicate_protection
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_deposit_withdrawal"
down_revision = "0007_ledger_duplicate_protection"
branch_labels = None
depends_on = None

transaction_type_enum = postgresql.ENUM(
    "TRANSFER", "DEPOSIT", "WITHDRAWAL", name="transaction_type", create_type=False
)


def upgrade() -> None:
    transaction_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "transactions",
        sa.Column(
            "transaction_type", transaction_type_enum, nullable=False, server_default="TRANSFER"
        ),
    )
    op.add_column("transactions", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("performed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_performed_by_user_id",
        "transactions",
        "users",
        ["performed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("transactions", "sender_account_id", nullable=True)
    op.alter_column("transactions", "receiver_account_id", nullable=True)

    op.create_check_constraint(
        "ck_transactions_accounts_match_type",
        "transactions",
        "(transaction_type = 'TRANSFER' AND sender_account_id IS NOT NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'DEPOSIT' AND sender_account_id IS NULL AND receiver_account_id IS NOT NULL)"
        " OR (transaction_type = 'WITHDRAWAL' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)",
    )

    # The server_default was only needed to backfill existing rows; new rows
    # should always specify transaction_type explicitly via the ORM.
    op.alter_column("transactions", "transaction_type", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_transactions_accounts_match_type", "transactions", type_="check")
    op.alter_column("transactions", "receiver_account_id", nullable=False)
    op.alter_column("transactions", "sender_account_id", nullable=False)
    op.drop_constraint("fk_transactions_performed_by_user_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "performed_by_user_id")
    op.drop_column("transactions", "note")
    op.drop_column("transactions", "transaction_type")
    transaction_type_enum.drop(op.get_bind(), checkfirst=True)
