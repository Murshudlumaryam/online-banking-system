"""Phase 7: scheduled_payments table (recurring transfers)

Revision ID: 0005_phase7_scheduled_payments
Revises: 0004_phase7_2fa
Create Date: 2026-07-16

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_phase7_scheduled_payments"
down_revision = "0004_phase7_2fa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    payment_frequency = postgresql.ENUM("DAILY", "WEEKLY", "MONTHLY", name="payment_frequency")
    payment_frequency.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scheduled_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("receiver_account_number", sa.String(34), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("frequency", postgresql.ENUM("DAILY", "WEEKLY", "MONTHLY", name="payment_frequency", create_type=False), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("last_failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_scheduled_payments_amount_positive"),
    )
    op.create_index("ix_scheduled_payments_customer_id", "scheduled_payments", ["customer_id"])
    op.create_index("ix_scheduled_payments_next_run_at", "scheduled_payments", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("scheduled_payments")
    op.execute("DROP TYPE IF EXISTS payment_frequency")
