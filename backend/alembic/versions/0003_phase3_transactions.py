"""Phase 3: exchange_rates, beneficiaries, transactions, transfer_confirmations, ledger_entries

Revision ID: 0003_phase3_transactions
Revises: 0002_phase2_accounts_cards
Create Date: 2026-07-13

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_phase3_transactions"
down_revision = "0002_phase2_accounts_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    beneficiary_status = postgresql.ENUM("ACTIVE", "DELETED", name="beneficiary_status")
    transaction_status = postgresql.ENUM(
        "PENDING", "SUCCESS", "FAILED", "REVERSED", name="transaction_status"
    )
    ledger_entry_type = postgresql.ENUM("DEBIT", "CREDIT", name="ledger_entry_type")
    beneficiary_status.create(op.get_bind(), checkfirst=True)
    transaction_status.create(op.get_bind(), checkfirst=True)
    ledger_entry_type.create(op.get_bind(), checkfirst=True)

    # --- exchange_rates ---
    op.create_table(
        "exchange_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "source_currency", "target_currency", "valid_from", name="uq_exchange_rate_pair_valid_from"
        ),
    )
    op.create_index(
        "ix_exchange_rates_pair_active", "exchange_rates", ["source_currency", "target_currency"],
        postgresql_where=sa.text("is_active = true"),
    )

    # --- beneficiaries ---
    op.create_table(
        "beneficiaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("beneficiary_account_number", sa.String(34), nullable=False),
        sa.Column("beneficiary_name", sa.String(150), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=True),
        sa.Column("status", postgresql.ENUM("ACTIVE", "DELETED", name="beneficiary_status", create_type=False), nullable=False, server_default="ACTIVE"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_beneficiaries_customer_id", "beneficiaries", ["customer_id"])

    # --- transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("reference_number", sa.String(48), nullable=False, unique=True),
        sa.Column("sender_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("receiver_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("exchange_rate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exchange_rates.id"), nullable=True),
        sa.Column("converted_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", postgresql.ENUM("PENDING", "SUCCESS", "FAILED", "REVERSED", name="transaction_status", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("otp_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.CheckConstraint("sender_account_id <> receiver_account_id", name="ck_transactions_distinct_accounts"),
    )
    op.create_index("ix_transactions_reference_number", "transactions", ["reference_number"])
    op.create_index("ix_transactions_sender_account_id", "transactions", ["sender_account_id"])
    op.create_index("ix_transactions_receiver_account_id", "transactions", ["receiver_account_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])

    # --- transfer_confirmations ---
    op.create_table(
        "transfer_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("otp_code_hash", sa.String(255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- ledger_entries ---
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_type", postgresql.ENUM("DEBIT", "CREDIT", name="ledger_entry_type", create_type=False), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("balance_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])


def downgrade() -> None:
    op.drop_table("ledger_entries")
    op.drop_table("transfer_confirmations")
    op.drop_table("transactions")
    op.drop_table("beneficiaries")
    op.drop_table("exchange_rates")
    op.execute("DROP TYPE IF EXISTS ledger_entry_type")
    op.execute("DROP TYPE IF EXISTS transaction_status")
    op.execute("DROP TYPE IF EXISTS beneficiary_status")
