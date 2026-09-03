import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.accounts.models import AccountStatus
from app.modules.customers.models import CustomerStatus


class UpdateCustomerStatusRequest(BaseModel):
    status: CustomerStatus


class CreateAccountRequest(BaseModel):
    customer_id: uuid.UUID
    account_type: str = Field(default="CHECKING", pattern="^(CHECKING|SAVINGS)$")
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class UpdateAccountStatusRequest(BaseModel):
    status: AccountStatus


class CreateCardRequest(BaseModel):
    account_id: uuid.UUID
    card_type: str = Field(default="DEBIT", pattern="^(DEBIT|CREDIT)$")
    validity_years: int = Field(default=4, ge=1, le=10)


class CreateExchangeRateRequest(BaseModel):
    source_currency: str = Field(min_length=3, max_length=3)
    target_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)

    @field_validator("source_currency", "target_currency")
    @classmethod
    def currency_uppercase(cls, value: str) -> str:
        return value.upper()


class LiveExchangeRateResponse(BaseModel):
    source_currency: str
    target_currency: str
    rate: Decimal


class AdminCreateCustomerRequest(BaseModel):
    """Lets an admin open an account for a customer who can't (or hasn't
    yet) self-registered — e.g. a walk-in branch customer. Distinct from
    RegisterCustomerRequest (auth module) mainly in who's allowed to call
    it and that it doesn't log the caller in afterward."""

    email: str = Field(min_length=3, max_length=255)
    # No default password: the admin sets a temporary one and is expected
    # to communicate it to the customer through a real out-of-band channel
    # (in person, a phone call) — never returned in this endpoint's
    # response or logged anywhere.
    temporary_password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    phone_number: str = Field(min_length=5, max_length=32)
    address: str | None = Field(default=None, max_length=500)
    national_id: str = Field(min_length=1, max_length=64)

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_must_be_past(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return value


class ReverseTransactionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
