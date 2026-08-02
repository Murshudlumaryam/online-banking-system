"""Phase 2: accounts, cards

Revision ID: 0002_phase2_accounts_cards
Revises: 0001_initial_phase1
Create Date: 2026-07-10

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_phase2_accounts_cards"
down_revision = "0001_initial_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    account_status = postgresql.ENUM(
        "ACTIVE", "BLOCKED", "CLOSED", "PENDING", name="account_status"
    )
    card_status = postgresql.ENUM("ACTIVE", "BLOCKED", "EXPIRED", name="card_status")
    account_status.create(op.get_bind(), checkfirst=True)
    card_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_number", sa.String(34), nullable=False, unique=True),
        sa.Column("account_type", sa.String(32), nullable=False, server_default="CHECKING"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("status", postgresql.ENUM("ACTIVE", "BLOCKED", "CLOSED", "PENDING", name="account_status", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_accounts_balance_non_negative"),
    )
    op.create_index("ix_accounts_customer_id", "accounts", ["customer_id"])
    op.create_index("ix_accounts_status", "accounts", ["status"])

    op.create_table(
        "cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("masked_card_number", sa.String(19), nullable=False),
        sa.Column("card_type", sa.String(16), nullable=False, server_default="DEBIT"),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("status", postgresql.ENUM("ACTIVE", "BLOCKED", "EXPIRED", name="card_status", create_type=False), nullable=False, server_default="ACTIVE"),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cards_account_id", "cards", ["account_id"])


def downgrade() -> None:
    op.drop_table("cards")
    op.drop_table("accounts")
    op.execute("DROP TYPE IF EXISTS card_status")
    op.execute("DROP TYPE IF EXISTS account_status")
