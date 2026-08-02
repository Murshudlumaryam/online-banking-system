import uuid
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
