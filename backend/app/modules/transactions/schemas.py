import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.ledger_entries.schemas import LedgerEntryResponse
from app.modules.transactions.models import TransactionStatus, TransactionType

# Shared upper bound, defense-in-depth against the amount/converted_amount
# columns' NUMERIC(18,2) capacity — see TransferMoneyRequest's comment
# below for the full rationale. Deposit/withdrawal share the same ceiling.
_MAX_AMOUNT = Decimal("1000000000")


def _validate_two_decimal_places(value: Decimal) -> Decimal:
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("amount must have at most 2 decimal places")
    return value


class TransferMoneyRequest(BaseModel):
    sender_account_id: uuid.UUID
    receiver_account_number: str = Field(min_length=5, max_length=34)
    # Upper bound is defense-in-depth, not a real product limit: the
    # `amount`/`converted_amount` DB columns are NUMERIC(18,2) (max
    # ~9.99...e15), and without this the only thing standing between an
    # absurd amount and a raw DB-level overflow error was the sender's
    # balance check — fine for a normal balance, but currency conversion
    # (amount * exchange_rate) could still overflow it even when the
    # original amount was under the sender's balance. Found during a
    # production-readiness audit; genuinely reachable (uncaught, surfaces as
    # a generic 500 via the catch-all handler — no data corruption, no
    # information leak, but a confusing error for something that should be
    # a clean 422). A real product-level per-transfer limit belongs here
    # too eventually; this is the safety ceiling, not that policy decision.
    amount: Decimal = Field(gt=0, le=_MAX_AMOUNT)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("amount")
    @classmethod
    def amount_max_two_decimal_places(cls, value: Decimal) -> Decimal:
        return _validate_two_decimal_places(value)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class DepositRequest(BaseModel):
    """Admin-only — see TransactionService.deposit's docstring for why this
    is an admin action rather than customer self-service in a system with
    no real payment-rail integration."""

    amount: Decimal = Field(gt=0, le=_MAX_AMOUNT)
    currency: str = Field(min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def amount_max_two_decimal_places(cls, value: Decimal) -> Decimal:
        return _validate_two_decimal_places(value)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class WithdrawalRequest(BaseModel):
    """Admin-only — see TransactionService.withdraw's docstring."""

    amount: Decimal = Field(gt=0, le=_MAX_AMOUNT)
    currency: str = Field(min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def amount_max_two_decimal_places(cls, value: Decimal) -> Decimal:
        return _validate_two_decimal_places(value)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class ConfirmTransferRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TransactionResponse(BaseModel):
    id: uuid.UUID
    reference_number: str
    transaction_type: TransactionType
    # Nullable: a DEPOSIT has no sender (money entered from outside this
    # closed-loop system) and a WITHDRAWAL has no receiver (money left it).
    sender_account_id: uuid.UUID | None
    receiver_account_id: uuid.UUID | None
    amount: Decimal
    currency: str
    converted_amount: Decimal | None
    status: TransactionStatus
    failure_reason: str | None
    note: str | None
    # Set only for CARD_PAYMENT — which card was charged.
    card_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TransactionDetailResponse(TransactionResponse):
    ledger_entries: list[LedgerEntryResponse] = Field(default_factory=list)


class InitiateTransferResponse(BaseModel):
    transaction: TransactionResponse
    otp_expires_in_seconds: int
    message: str = "An OTP has been sent to confirm this transfer."


class ResendOtpResponse(BaseModel):
    otp_expires_in_seconds: int
    message: str = "A new OTP has been sent. The previous code no longer works."
