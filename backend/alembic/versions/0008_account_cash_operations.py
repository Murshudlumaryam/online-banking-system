"""Add admin cash deposit and withdrawal operations

Revision ID: 0008_account_cash_operations
Revises: 0007_ledger_entry_uniqueness
Create Date: 2026-08-03

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_account_cash_operations"
down_revision = "0007_ledger_entry_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    operation_type = postgresql.ENUM(
        "DEPOSIT",
        "WITHDRAWAL",
        name="cash_operation_type",
    )
    operation_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "account_cash_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", operation_type, nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("performed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_account_cash_operations_amount_positive"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["performed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_cash_operations_account_id", "account_cash_operations", ["account_id"])
    op.create_index(
        "ix_account_cash_operations_performed_by_user_id",
        "account_cash_operations",
        ["performed_by_user_id"],
    )
    op.create_index("ix_account_cash_operations_created_at", "account_cash_operations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_account_cash_operations_created_at", table_name="account_cash_operations")
    op.drop_index("ix_account_cash_operations_performed_by_user_id", table_name="account_cash_operations")
    op.drop_index("ix_account_cash_operations_account_id", table_name="account_cash_operations")
    op.drop_table("account_cash_operations")
    postgresql.ENUM(name="cash_operation_type").drop(op.get_bind(), checkfirst=True)
