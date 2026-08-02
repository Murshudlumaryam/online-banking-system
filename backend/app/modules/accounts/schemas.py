import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.modules.accounts.models import AccountStatus


class AccountResponse(BaseModel):
    id: uuid.UUID
    account_number: str
    account_type: str
    currency: str
    balance: Decimal
    status: AccountStatus

    model_config = {"from_attributes": True}


class AccountBalanceResponse(BaseModel):
    account_id: uuid.UUID
    currency: str
    balance: Decimal
