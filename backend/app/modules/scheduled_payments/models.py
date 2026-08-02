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
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentFrequency(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class ScheduledPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A standing transfer authorization the customer set up once. Execution
    (see app.background_tasks.tasks.execute_scheduled_payments_task) skips
    the interactive OTP step — the customer's authorization was already
    captured when this row was created, not re-confirmed every run.
    """

    __tablename__ = "scheduled_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_scheduled_payments_amount_positive"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    receiver_account_number: Mapped[str] = mapped_column(String(34), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    frequency: Mapped[PaymentFrequency] = mapped_column(
        Enum(PaymentFrequency, name="payment_frequency", native_enum=True), nullable=False
    )
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )
    last_failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
