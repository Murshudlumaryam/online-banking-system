import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer
from app.modules.scheduled_payments.schemas import (
    CreateScheduledPaymentRequest,
    ScheduledPaymentResponse,
)
from app.modules.scheduled_payments.service import ScheduledPaymentService

router = APIRouter(prefix="/api/v1/scheduled-payments", tags=["scheduled-payments"])


@router.get(
    "", response_model=list[ScheduledPaymentResponse], summary="List the customer's scheduled payments"
)
async def list_scheduled_payments(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> list[ScheduledPaymentResponse]:
    service = ScheduledPaymentService(session)
    schedules = await service.list_for_customer(customer)
    return [ScheduledPaymentResponse.model_validate(s) for s in schedules]


@router.post(
    "",
    response_model=ScheduledPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a recurring/scheduled payment (executes without interactive OTP)",
)
async def create_scheduled_payment(
    payload: CreateScheduledPaymentRequest,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> ScheduledPaymentResponse:
    service = ScheduledPaymentService(session)
    schedule = await service.create(customer, payload)
    return ScheduledPaymentResponse.model_validate(schedule)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a scheduled payment",
)
async def cancel_scheduled_payment(
    schedule_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> None:
    service = ScheduledPaymentService(session)
    await service.cancel(customer, schedule_id)
