"""Add reversal tracking to transactions

Adds transactions.reversal_of_transaction_id (nullable, self-referencing FK)
so a REVERSED transaction and the new transaction that reversed it can be
traced back to each other, and transactions.reversed_by_user_id to record
which admin performed the reversal.

Revision ID: 0009_transaction_reversal
Revises: 0008_deposit_withdrawal
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_transaction_reversal"
down_revision = "0008_deposit_withdrawal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("reversal_of_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_reversal_of_transaction_id",
        "transactions",
        "transactions",
        ["reversal_of_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # A transaction can be the *source* of at most one reversal — you
    # cannot reverse the same original transfer twice.
    op.create_unique_constraint(
        "uq_transactions_reversal_of_transaction_id",
        "transactions",
        ["reversal_of_transaction_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transactions_reversal_of_transaction_id", "transactions", type_="unique"
    )
    op.drop_constraint(
        "fk_transactions_reversal_of_transaction_id", "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "reversal_of_transaction_id")
