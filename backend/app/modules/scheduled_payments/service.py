import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.core.exceptions import (
    AccountNotActiveError,
    CurrencyMismatchError,
    NotFoundError,
)
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.models import Customer
from app.modules.scheduled_payments.models import ScheduledPayment
from app.modules.scheduled_payments.repository import ScheduledPaymentRepository
from app.modules.scheduled_payments.schemas import CreateScheduledPaymentRequest


class ScheduledPaymentService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._schedules = ScheduledPaymentRepository(session)
        self._accounts = AccountRepository(session)

    async def list_for_customer(self, customer: Customer) -> list[ScheduledPayment]:
        return await self._schedules.list_for_customer(customer.id)

    async def create(
        self, customer: Customer, payload: CreateScheduledPaymentRequest
    ) -> ScheduledPayment:
        sender = await self._accounts.get_by_id(payload.sender_account_id)
        if sender is None or sender.customer_id != customer.id:
            raise NotFoundError("Sender account not found")
        if sender.status != AccountStatus.ACTIVE:
            raise AccountNotActiveError(which="sender account")
        if payload.currency != sender.currency:
            raise CurrencyMismatchError(sender.currency, payload.currency)

        schedule = self._schedules.create(
            customer_id=customer.id,
            sender_account_id=sender.id,
            receiver_account_number=payload.receiver_account_number,
            amount=payload.amount,
            currency=payload.currency,
            frequency=payload.frequency,
            first_run_at=payload.start_at or datetime.now(timezone.utc),
        )
        await self._session.commit()
        await self._session.refresh(schedule)

        write_audit_log_task.delay(
            str(customer.user_id),
            "SCHEDULED_PAYMENT_CREATED",
            "scheduled_payment",
            str(schedule.id),
            None,
            {"frequency": payload.frequency.value, "amount": str(payload.amount)},
        )
        return schedule

    async def cancel(self, customer: Customer, schedule_id: uuid.UUID) -> ScheduledPayment:
        schedule = await self._schedules.get_by_id(schedule_id)
        if schedule is None or schedule.customer_id != customer.id:
            raise NotFoundError("Scheduled payment not found")

        schedule.is_active = False
        await self._schedules.save(schedule)
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id), "SCHEDULED_PAYMENT_CANCELLED", "scheduled_payment",
            str(schedule.id), None, None,
        )
        return schedule
