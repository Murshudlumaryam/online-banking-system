import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class TransactionType(str, enum.Enum):
    TRANSFER = "TRANSFER"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    CARD_PAYMENT = "CARD_PAYMENT"


class Transaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        # NULL-safe: Postgres treats a CHECK as satisfied when it evaluates
        # to NULL (unknown), which is exactly what happens here when either
        # side is NULL (a DEPOSIT/WITHDRAWAL) — so this still only rejects
        # the case that actually matters: a TRANSFER naming the same
        # account as both sender and receiver.
        CheckConstraint("sender_account_id <> receiver_account_id", name="ck_transactions_distinct_accounts"),
        # A DEPOSIT/WITHDRAWAL is inherently single-sided (money crossing
        # the boundary of this closed-loop system, not moving between two
        # of its own accounts) — exactly one of sender/receiver must be set
        # for those types, and both must be set for a TRANSFER.
        CheckConstraint(
            "(transaction_type = 'TRANSFER' AND sender_account_id IS NOT NULL AND receiver_account_id IS NOT NULL)"
            " OR (transaction_type = 'DEPOSIT' AND sender_account_id IS NULL AND receiver_account_id IS NOT NULL)"
            " OR (transaction_type = 'WITHDRAWAL' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)"
            " OR (transaction_type = 'CARD_PAYMENT' AND sender_account_id IS NOT NULL AND receiver_account_id IS NULL)",
            name="ck_transactions_accounts_match_type",
        ),
    )

    reference_number: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type", native_enum=True),
        nullable=False,
        default=TransactionType.TRANSFER,
        index=True,
    )
    # Nullable because a DEPOSIT has no sender (money enters from outside
    # this closed-loop system) and a WITHDRAWAL has no receiver (money
    # leaves it) — see the transaction_type CHECK constraint above for the
    # exact rule tying these to `transaction_type`.
    sender_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    receiver_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exchange_rates.id"), nullable=True
    )
    converted_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status", native_enum=True),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
    )
    otp_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text operational note — e.g. "Cash deposit at Nasimi branch" or
    # "ATM withdrawal reversal". Unused for ordinary customer transfers;
    # set for admin-initiated DEPOSIT/WITHDRAWAL operations.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who initiated this — NULL for a customer's own transfer (the customer
    # is already identifiable via the sender account's owner). Set to the
    # admin's user id for a DEPOSIT/WITHDRAWAL, since those represent an
    # admin acting on a customer's account rather than the customer acting
    # on their own.
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set on the NEW transaction created by an admin reversal — points back
    # at the original transaction it reverses. The original transaction's
    # own status is separately set to REVERSED (see TransactionService
    # .reverse_transaction) rather than mutating its amount/ledger, since
    # ledger rows are append-only and never edited after the fact.
    reversal_of_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    # Set only for CARD_PAYMENT — which specific card was swiped/charged.
    # NULL for every other transaction_type (a transfer/deposit/withdrawal
    # isn't tied to a card at all).
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TransferConfirmation(UUIDPrimaryKeyMixin, Base):
    """One-to-one OTP challenge attached to a PENDING transaction."""

    __tablename__ = "transfer_confirmations"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    otp_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
