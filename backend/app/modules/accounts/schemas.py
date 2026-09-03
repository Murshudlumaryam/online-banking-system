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
    # Populated only where the caller actually eager-loaded the
    # relationship (admin listings) — the customer's own account views
    # don't need to say "this is your account" back to them. See
    # AdminService.list_accounts and get_customer_accounts, which use
    # selectinload for exactly this.
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None

    model_config = {"from_attributes": True}


class AccountBalanceResponse(BaseModel):
    account_id: uuid.UUID
    currency: str
    balance: Decimal
