"""Add card soft-delete and the CARD_PAYMENT transaction_type value

Split from the CHECK-constraint update (see 0011) because Postgres/asyncpg
refuses to reference a newly-added enum value in the same transaction it
was added in ("unsafe use of new value ... New enum values must be
committed before they can be used") — this migration only adds the value
and commits; 0011 is the one that actually uses it in a CHECK constraint.

Revision ID: 0010_card_delete_and_payment_type
Revises: 0009_transaction_reversal
Create Date: 2026-08-16

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_card_delete_payment"
down_revision = "0009_transaction_reversal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'CARD_PAYMENT'")

    op.add_column("transactions", sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_transactions_card_id", "transactions", "cards", ["card_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_card_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "card_id")
    # CARD_PAYMENT is intentionally left in the transaction_type enum on
    # downgrade — Postgres cannot drop a single enum value without
    # rebuilding the whole type, and 0011's downgrade already removes the
    # CHECK constraint that was the only thing actually using it.
    op.drop_column("cards", "deleted_at")
