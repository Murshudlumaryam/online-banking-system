from datetime import datetime, timedelta, timezone

import pytest

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository


async def _make_active_account(db_session, customer_id, account_number, currency="AZN", balance="500.00"):
    repo = AccountRepository(db_session)
    account = repo.create(
        customer_id=customer_id, account_number=account_number, account_type="CHECKING", currency=currency
    )
    await db_session.flush()
    account.status = AccountStatus.ACTIVE
    account.balance = balance
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_execute_scheduled_transfer_moves_money_immediately_no_otp(
    db_session, registered_customer: dict
):
    """Exercises TransactionService.execute_scheduled_transfer directly —
    the OTP-free execution path used by the Celery beat sweep."""
    from app.modules.transactions.models import TransactionStatus
    from app.modules.transactions.service import TransactionService

    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "SCHEDEXEC01", "AZN", "200.00")
    receiver = await _make_active_account(db_session, customer.id, "SCHEDEXEC02", "AZN", "0.00")

    service = TransactionService(db_session)
    transaction = await service.execute_scheduled_transfer(
        customer,
        sender_account_id=sender.id,
        receiver_account_number="SCHEDEXEC02",
        amount=30,
        currency="AZN",
    )

    assert transaction.status == TransactionStatus.SUCCESS
    assert transaction.otp_verified is False  # pre-authorized, not interactively confirmed

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == 170
    assert receiver.balance == 30


@pytest.mark.asyncio
async def test_execute_scheduled_transfer_rejects_insufficient_balance(
    db_session, registered_customer: dict
):
    from app.core.exceptions import InsufficientBalanceError
    from app.modules.transactions.service import TransactionService

    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "SCHEDEXEC03", "AZN", "5.00")
    await _make_active_account(db_session, customer.id, "SCHEDEXEC04", "AZN", "0.00")

    service = TransactionService(db_session)
    with pytest.raises(InsufficientBalanceError):
        await service.execute_scheduled_transfer(
            customer,
            sender_account_id=sender.id,
            receiver_account_number="SCHEDEXEC04",
            amount=100,
            currency="AZN",
        )


@pytest.mark.asyncio
async def test_scheduled_payments_sweep_executes_due_schedules_and_advances_next_run():
    """
    Full end-to-end test of the Celery beat task's underlying async sweep.
    Uses a real committed setup (the sweep uses AsyncSessionLocal, a
    separate connection from the rollback-isolated db_session fixture —
    same pattern as test_concurrency.py) and cleans up manually.
    """
    import uuid as uuid_module
    from datetime import date

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _execute_scheduled_payments_async
    from app.modules.accounts.models import Account
    from app.modules.accounts.repository import AccountRepository
    from app.modules.customers.models import Customer
    from app.modules.customers.repository import CustomerRepository
    from app.modules.ledger_entries.models import LedgerEntry
    from app.modules.scheduled_payments.models import PaymentFrequency, ScheduledPayment
    from app.modules.scheduled_payments.repository import ScheduledPaymentRepository
    from app.modules.transactions.models import Transaction
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"sweep_sched_{unique}@example.com", password_hash="x")
        await setup.flush()
        customers = CustomerRepository(setup)
        customer = customers.create(
            user_id=user.id, first_name="Sweep", last_name="Schedule",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000002",
        )
        await setup.flush()

        accounts = AccountRepository(setup)
        sender = accounts.create(
            customer_id=customer.id, account_number=f"SWPSC{unique}A", account_type="CHECKING", currency="AZN"
        )
        receiver = accounts.create(
            customer_id=customer.id, account_number=f"SWPSC{unique}B", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = 100
        receiver.status = AccountStatus.ACTIVE
        receiver.balance = 0

        schedules = ScheduledPaymentRepository(setup)
        schedule = schedules.create(
            customer_id=customer.id,
            sender_account_id=sender.id,
            receiver_account_number=receiver.account_number,
            amount=20,
            currency="AZN",
            frequency=PaymentFrequency.DAILY,
            first_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already due
        )
        await setup.commit()
        schedule_id, sender_id, receiver_id, customer_id, user_id = (
            schedule.id, sender.id, receiver.id, customer.id, user.id,
        )
        original_next_run = schedule.next_run_at

    try:
        result = await _execute_scheduled_payments_async()
        assert result["executed"] >= 1

        async with session_factory() as verify:
            accounts = AccountRepository(verify)
            final_sender = await accounts.get_by_id(sender_id)
            final_receiver = await accounts.get_by_id(receiver_id)
            assert final_sender.balance == 80
            assert final_receiver.balance == 20

            schedules = ScheduledPaymentRepository(verify)
            final_schedule = await schedules.get_by_id(schedule_id)
            assert final_schedule.last_executed_at is not None
            assert final_schedule.last_transaction_id is not None
            assert final_schedule.next_run_at > original_next_run
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(ScheduledPayment).where(ScheduledPayment.id == schedule_id))
            await cleanup.execute(
                delete(LedgerEntry).where(LedgerEntry.account_id.in_([sender_id, receiver_id]))
            )
            await cleanup.execute(
                delete(Transaction).where(
                    (Transaction.sender_account_id == sender_id)
                    | (Transaction.receiver_account_id == sender_id)
                )
            )
            await cleanup.execute(delete(Account).where(Account.id.in_([sender_id, receiver_id])))
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_payments_sweep_records_failure_without_raising():
    """A schedule with insufficient balance should be marked failed (with a
    reason) and its next_run_at advanced, not raise or get stuck retrying
    every sweep."""
    import uuid as uuid_module
    from datetime import date

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _execute_scheduled_payments_async
    from app.modules.accounts.models import Account
    from app.modules.accounts.repository import AccountRepository
    from app.modules.customers.models import Customer
    from app.modules.customers.repository import CustomerRepository
    from app.modules.scheduled_payments.models import PaymentFrequency, ScheduledPayment
    from app.modules.scheduled_payments.repository import ScheduledPaymentRepository
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"sweep_fail_{unique}@example.com", password_hash="x")
        await setup.flush()
        customers = CustomerRepository(setup)
        customer = customers.create(
            user_id=user.id, first_name="Sweep", last_name="Fail",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000003",
        )
        await setup.flush()

        accounts = AccountRepository(setup)
        sender = accounts.create(
            customer_id=customer.id, account_number=f"SWPFAIL{unique}A", account_type="CHECKING", currency="AZN"
        )
        receiver = accounts.create(
            customer_id=customer.id, account_number=f"SWPFAIL{unique}B", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = 5  # not enough for the scheduled amount below
        receiver.status = AccountStatus.ACTIVE

        schedules = ScheduledPaymentRepository(setup)
        schedule = schedules.create(
            customer_id=customer.id,
            sender_account_id=sender.id,
            receiver_account_number=receiver.account_number,
            amount=50,
            currency="AZN",
            frequency=PaymentFrequency.DAILY,
            first_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        await setup.commit()
        schedule_id, sender_id, receiver_id, customer_id, user_id = (
            schedule.id, sender.id, receiver.id, customer.id, user.id,
        )

    try:
        result = await _execute_scheduled_payments_async()
        assert result["failed"] >= 1

        async with session_factory() as verify:
            schedules = ScheduledPaymentRepository(verify)
            final_schedule = await schedules.get_by_id(schedule_id)
            assert final_schedule.last_failure_reason is not None
            assert final_schedule.last_transaction_id is None
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(ScheduledPayment).where(ScheduledPayment.id == schedule_id))
            await cleanup.execute(delete(Account).where(Account.id.in_([sender_id, receiver_id])))
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
