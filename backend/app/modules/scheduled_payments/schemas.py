import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.scheduled_payments.models import PaymentFrequency


class CreateScheduledPaymentRequest(BaseModel):
    sender_account_id: uuid.UUID
    receiver_account_number: str = Field(min_length=5, max_length=34)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    frequency: PaymentFrequency
    start_at: datetime | None = Field(
        default=None, description="First run time; defaults to now (executes on the next sweep)."
    )

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class ScheduledPaymentResponse(BaseModel):
    id: uuid.UUID
    sender_account_id: uuid.UUID
    receiver_account_number: str
    amount: Decimal
    currency: str
    frequency: PaymentFrequency
    next_run_at: datetime
    is_active: bool
    last_executed_at: datetime | None
    last_transaction_id: uuid.UUID | None
    last_failure_reason: str | None

    model_config = {"from_attributes": True}
