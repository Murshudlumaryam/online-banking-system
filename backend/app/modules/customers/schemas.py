import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.accounts.schemas import AccountResponse
from app.modules.customers.models import CustomerStatus


class CustomerProfileResponse(BaseModel):
    id: uuid.UUID
    customer_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    phone_number: str
    address: str | None
    national_id: str | None
    status: CustomerStatus
    # Lives on the related User row, not Customer — 2FA is an
    # authentication concept, not a customer-profile one. Populated
    # explicitly by the router (see get_my_profile), not by
    # model_validate(customer) alone, since Customer has no direct column
    # for it.
    totp_enabled: bool = False

    model_config = {"from_attributes": True}


class UpdateCustomerProfileRequest(BaseModel):
    """
    Only phone_number and address are updatable by the customer — matches the
    TD's "Update allowed profile fields such as phone number and address".
    Identity fields (name, DOB, national ID, customer number) are immutable
    through this endpoint; changing them is an admin-only operation.
    """

    phone_number: str | None = Field(default=None, min_length=5, max_length=32)
    address: str | None = Field(default=None, max_length=500)


class CurrencyBalance(BaseModel):
    currency: str
    total_balance: Decimal


class DashboardResponse(BaseModel):
    customer_number: str
    full_name: str
    total_accounts: int
    balances_by_currency: list[CurrencyBalance]
    accounts: list[AccountResponse]
