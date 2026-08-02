import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.ledger_entries.schemas import LedgerEntryResponse
from app.modules.transactions.models import TransactionStatus


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
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("amount")
    @classmethod
    def amount_max_two_decimal_places(cls, value: Decimal) -> Decimal:
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return value

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class ConfirmTransferRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TransactionResponse(BaseModel):
    id: uuid.UUID
    reference_number: str
    sender_account_id: uuid.UUID
    receiver_account_id: uuid.UUID
    amount: Decimal
    currency: str
    converted_amount: Decimal | None
    status: TransactionStatus
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TransactionDetailResponse(TransactionResponse):
    ledger_entries: list[LedgerEntryResponse] = Field(default_factory=list)


class InitiateTransferResponse(BaseModel):
    transaction: TransactionResponse
    otp_expires_in_seconds: int
    message: str = "An OTP has been sent to confirm this transfer."
