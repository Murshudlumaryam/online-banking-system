import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.ledger_entries.schemas import LedgerEntryResponse
from app.modules.transactions.models import TransactionStatus


class TransferMoneyRequest(BaseModel):
    sender_account_id: uuid.UUID
    receiver_account_number: str = Field(min_length=5, max_length=34)
    amount: Decimal = Field(gt=0)
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
