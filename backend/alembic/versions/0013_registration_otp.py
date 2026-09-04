"""Add email verification (registration OTP)

Adds:
- users.email_verified — defaults to TRUE at the *database* level so
  every existing account (registered before this feature existed) stays
  able to log in unaffected. New signups get FALSE explicitly from
  application code (see UserRepository.create), which is what actually
  gates them behind email verification — the column default is purely a
  safety net for the backfill, not the enforcement mechanism.
- registration_confirmations — one-to-one OTP challenge per user,
  structurally identical to transfer_confirmations (hash, expiry,
  attempts, UNIQUE FK) rather than a shared generic OTP table.

Revision ID: 0013_registration_otp
Revises: 0012_audit_log_fields
Create Date: 2026-09-03

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_registration_otp"
down_revision = "0012_audit_log_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # The server_default above only controls what NEW rows get if the
    # application doesn't specify a value; it does not implicitly apply
    # to allow removing it once every existing row has been backfilled to
    # TRUE by the ADD COLUMN itself. Drop it so new inserts are forced to
    # state the value explicitly (matching every other boolean column on
    # this table) rather than silently defaulting to "verified".
    op.alter_column("users", "email_verified", server_default=None)

    op.create_table(
        "registration_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("otp_code_hash", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("registration_confirmations")
    op.drop_column("users", "email_verified")
