from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.dependencies import require_customer
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerProfileResponse,
    DashboardResponse,
    UpdateCustomerProfileRequest,
)
from app.modules.customers.service import CustomerService
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get("/me", response_model=CustomerProfileResponse, summary="Get the current customer profile")
async def get_my_profile(
    customer: Customer = Depends(get_current_customer),
    current_user: User = Depends(require_customer),
) -> CustomerProfileResponse:
    return CustomerProfileResponse(
        **CustomerProfileResponse.model_validate(customer).model_dump(exclude={"totp_enabled"}),
        totp_enabled=current_user.totp_enabled,
    )


@router.patch(
    "/me",
    response_model=CustomerProfileResponse,
    summary="Update allowed profile fields (phone number, address)",
)
async def update_my_profile(
    payload: UpdateCustomerProfileRequest,
    customer: Customer = Depends(get_current_customer),
    current_user: User = Depends(require_customer),
    session: AsyncSession = Depends(get_db),
) -> CustomerProfileResponse:
    service = CustomerService(session)
    updated = await service.update_profile(customer, payload)
    return CustomerProfileResponse(
        **CustomerProfileResponse.model_validate(updated).model_dump(exclude={"totp_enabled"}),
        totp_enabled=current_user.totp_enabled,
    )


@router.get(
    "/me/dashboard",
    response_model=DashboardResponse,
    summary="Get an account/balance summary for the current customer",
)
async def get_my_dashboard(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    service = CustomerService(session)
    return await service.get_dashboard(customer)
