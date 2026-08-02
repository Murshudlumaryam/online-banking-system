import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduled_payments.models import PaymentFrequency, ScheduledPayment

_FREQUENCY_TIMEDELTA = {
    PaymentFrequency.DAILY: timedelta(days=1),
    PaymentFrequency.WEEKLY: timedelta(weeks=1),
    PaymentFrequency.MONTHLY: timedelta(days=30),  # simple, predictable — not calendar-month-aware
}


def advance_next_run(current: datetime, frequency: PaymentFrequency) -> datetime:
    return current + _FREQUENCY_TIMEDELTA[frequency]


class ScheduledPaymentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, schedule_id: uuid.UUID) -> ScheduledPayment | None:
        result = await self._session.execute(
            select(ScheduledPayment).where(ScheduledPayment.id == schedule_id)
        )
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[ScheduledPayment]:
        result = await self._session.execute(
            select(ScheduledPayment)
            .where(ScheduledPayment.customer_id == customer_id)
            .order_by(ScheduledPayment.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_due(self, *, at: datetime | None = None) -> list[ScheduledPayment]:
        now = at or datetime.now(timezone.utc)
        result = await self._session.execute(
            select(ScheduledPayment).where(
                ScheduledPayment.is_active.is_(True), ScheduledPayment.next_run_at <= now
            )
        )
        return list(result.scalars().all())

    def create(
        self,
        *,
        customer_id: uuid.UUID,
        sender_account_id: uuid.UUID,
        receiver_account_number: str,
        amount: Decimal,
        currency: str,
        frequency: PaymentFrequency,
        first_run_at: datetime,
    ) -> ScheduledPayment:
        schedule = ScheduledPayment(
            customer_id=customer_id,
            sender_account_id=sender_account_id,
            receiver_account_number=receiver_account_number,
            amount=amount,
            currency=currency,
            frequency=frequency,
            next_run_at=first_run_at,
        )
        self._session.add(schedule)
        return schedule

    async def save(self, schedule: ScheduledPayment) -> None:
        self._session.add(schedule)
        await self._session.flush()

    async def record_success(self, schedule: ScheduledPayment, transaction_id: uuid.UUID) -> None:
        schedule.last_executed_at = datetime.now(timezone.utc)
        schedule.last_transaction_id = transaction_id
        schedule.last_failure_reason = None
        schedule.next_run_at = advance_next_run(schedule.next_run_at, schedule.frequency)
        self._session.add(schedule)

    async def record_failure(self, schedule: ScheduledPayment, reason: str) -> None:
        schedule.last_executed_at = datetime.now(timezone.utc)
        schedule.last_failure_reason = reason[:500]
        # Still advance next_run_at — a persistently-failing schedule (e.g.
        # insufficient balance) should retry next cycle, not spin constantly.
        schedule.next_run_at = advance_next_run(schedule.next_run_at, schedule.frequency)
        self._session.add(schedule)
