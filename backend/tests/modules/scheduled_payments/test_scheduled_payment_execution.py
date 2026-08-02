"""
Tests for the scheduled-payment execution sweep. Like test_concurrency.py,
this bypasses the shared rollback-isolated `db_session` fixture because
`_execute_scheduled_payments_async` opens its own connection via
AsyncSessionLocal (exactly as it does in production, running unattended on
a timer) — a separate connection can't see uncommitted work from the test
fixture's connection. Rows are committed for real and cleaned up manually.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.background_tasks.tasks import _execute_scheduled_payments_async
from app.modules.accounts.models import Account, AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.audit_logs.models import AuditLog
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.ledger_entries.models import LedgerEntry
from app.modules.scheduled_payments.models import PaymentFrequency, ScheduledPayment
from app.modules.scheduled_payments.repository import ScheduledPaymentRepository
from app.modules.transactions.models import Transaction
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


class _ScheduledPaymentTestHarness:
    """Sets up one real, committed customer + two accounts + a due schedule,
    and tears everything down afterward. Used as an async context manager."""

    def __init__(self, *, initial_sender_balance: int = 100):
        self.engine = create_async_engine(TEST_DATABASE_URL)
        self.session_factory = async_sessionmaker(bind=self.engine, expire_on_commit=False)
        self.initial_sender_balance = initial_sender_balance
        self.user_id = None
        self.customer_id = None
        self.sender_id = None
        self.receiver_id = None
        self.schedule_id = None

    async def __aenter__(self):
        unique = uuid.uuid4().hex[:10]
        async with self.session_factory() as session:
            users = UserRepository(session)
            user = users.create(email=f"sched_exec_{unique}@example.com", password_hash="x")
            await session.flush()

            customers = CustomerRepository(session)
            customer = customers.create(
                user_id=user.id,
                first_name="Sched",
                last_name="Exec",
                date_of_birth=date(1990, 1, 1),
                phone_number="+994500000002",
            )
            await session.flush()

            accounts = AccountRepository(session)
            sender = accounts.create(
                customer_id=customer.id, account_number=f"SCHEXE{unique}A",
                account_type="CHECKING", currency="AZN",
            )
            receiver = accounts.create(
                customer_id=customer.id, account_number=f"SCHEXE{unique}B",
                account_type="CHECKING", currency="AZN",
            )
            await session.flush()
            sender.status = AccountStatus.ACTIVE
            sender.balance = self.initial_sender_balance
            receiver.status = AccountStatus.ACTIVE

            schedules = ScheduledPaymentRepository(session)
            schedule = schedules.create(
                customer_id=customer.id,
                sender_account_id=sender.id,
                receiver_account_number=receiver.account_number,
                amount=30,
                currency="AZN",
                frequency=PaymentFrequency.DAILY,
                first_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already due
            )
            await session.commit()

            self.user_id = user.id
            self.customer_id = customer.id
            self.sender_id = sender.id
            self.receiver_id = receiver.id
            self.schedule_id = schedule.id
        return self

    async def __aexit__(self, *exc_info):
        await self.engine.dispose()
        # Use a brand-new engine/connection for cleanup — reusing the same
        # engine object after several preceding operations in this test
        # (including a separate engine's calls in between) has been
        # unreliable in this sandbox's asyncpg + greenlet setup; a fresh
        # engine sidesteps it entirely.
        cleanup_engine = create_async_engine(TEST_DATABASE_URL)
        cleanup_session_factory = async_sessionmaker(bind=cleanup_engine, expire_on_commit=False)
        async with cleanup_session_factory() as session:
            await session.execute(
                delete(LedgerEntry).where(LedgerEntry.account_id.in_([self.sender_id, self.receiver_id]))
            )
            await session.execute(
                delete(ScheduledPayment).where(ScheduledPayment.id == self.schedule_id)
            )
            await session.execute(
                delete(Transaction).where(
                    (Transaction.sender_account_id == self.sender_id)
                    | (Transaction.receiver_account_id == self.receiver_id)
                )
            )
            await session.execute(
                delete(Account).where(Account.id.in_([self.sender_id, self.receiver_id]))
            )
            await session.execute(delete(Customer).where(Customer.id == self.customer_id))
            await session.execute(delete(AuditLog).where(AuditLog.user_id == self.user_id))
            await session.execute(delete(User).where(User.id == self.user_id))
            await session.commit()
        await cleanup_engine.dispose()


@pytest.mark.asyncio
async def test_execute_scheduled_payments_moves_money_and_advances_next_run():
    async with _ScheduledPaymentTestHarness() as harness:
        result = await _execute_scheduled_payments_async()
        assert result["executed"] >= 1
        assert result["failed"] == 0

        async with harness.session_factory() as verify_session:
            accounts = AccountRepository(verify_session)
            sender = await accounts.get_by_id(harness.sender_id)
            receiver = await accounts.get_by_id(harness.receiver_id)
            assert sender.balance == 70
            assert receiver.balance == 30

            schedules = ScheduledPaymentRepository(verify_session)
            schedule = await schedules.get_by_id(harness.schedule_id)
            assert schedule.last_executed_at is not None
            assert schedule.last_transaction_id is not None
            assert schedule.next_run_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_execute_scheduled_payments_records_failure_without_raising():
    async with _ScheduledPaymentTestHarness(initial_sender_balance=0) as harness:
        result = await _execute_scheduled_payments_async()
        assert result["failed"] >= 1

        async with harness.session_factory() as verify_session:
            schedules = ScheduledPaymentRepository(verify_session)
            schedule = await schedules.get_by_id(harness.schedule_id)
            assert schedule.last_failure_reason is not None
            assert "balance" in schedule.last_failure_reason.lower()
            # Still advances so a persistently-failing schedule doesn't spin.
            assert schedule.next_run_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_execute_scheduled_payments_ignores_not_yet_due():
    from sqlalchemy import select

    async with _ScheduledPaymentTestHarness() as harness:
        # Push this schedule's next_run_at into the future — the sweep
        # should ignore it.
        async with harness.session_factory() as session:
            schedules = ScheduledPaymentRepository(session)
            schedule = await schedules.get_by_id(harness.schedule_id)
            schedule.next_run_at = datetime.now(timezone.utc) + timedelta(days=1)
            await schedules.save(schedule)
            await session.commit()

        await _execute_scheduled_payments_async()

        async with harness.session_factory() as verify_session:
            result_check = await verify_session.execute(
                select(ScheduledPayment).where(ScheduledPayment.id == harness.schedule_id)
            )
            schedule = result_check.scalar_one()
            assert schedule.last_executed_at is None  # never touched
