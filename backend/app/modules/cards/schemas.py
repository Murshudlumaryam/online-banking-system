import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.cards.models import CardStatus


class CardResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    masked_card_number: str
    card_type: str
    expiry_date: date
    status: CardStatus

    model_config = {"from_attributes": True}


class CardPaymentRequest(BaseModel):
    """A simulated card purchase — see CardService.pay_with_card's
    docstring for what this does and doesn't represent."""

    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))
    currency: str = Field(min_length=3, max_length=3)
    merchant_name: str = Field(min_length=1, max_length=200)

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
