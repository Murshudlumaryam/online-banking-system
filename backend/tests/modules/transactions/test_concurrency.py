"""
Genuine concurrency test for the transfer-confirmation race condition.

Unlike the other tests in this suite, this one deliberately does NOT rely on
the shared `db_session` fixture: that fixture binds every operation in a test
to a single AsyncSession/connection, which is exactly what production code
never does under real concurrent load. To prove the pessimistic-locking
strategy (SELECT ... FOR UPDATE, ordered by id) actually prevents a
double-spend, we need two independent connections racing against the same
committed rows, the same way two concurrent HTTP requests would in
production.

This test commits real rows for real (not inside the rollback-only
transaction the rest of the suite uses) and cleans them up manually at the
end.
"""
import asyncio
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import generate_otp_code, hash_otp_code
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.repository import CustomerRepository
from app.modules.transactions.models import Transaction, TransactionStatus
from app.modules.transactions.repository import (
    TransactionRepository,
    TransferConfirmationRepository,
)
from app.modules.transactions.service import TransactionService
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_concurrent_confirm_cannot_double_spend():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    # --- Seed real, committed data on its own connection ---
    async with session_factory() as setup_session:
        users = UserRepository(setup_session)
        customers = CustomerRepository(setup_session)
        accounts = AccountRepository(setup_session)

        unique = uuid.uuid4().hex[:10]
        user = users.create(email=f"race_{unique}@example.com", password_hash="x")
        await setup_session.flush()
        customer = customers.create(
            user_id=user.id,
            first_name="Race",
            last_name="Condition",
            date_of_birth=date(1990, 1, 1),
            phone_number="+994500000000",
        )
        await setup_session.flush()

        sender = accounts.create(
            customer_id=customer.id, account_number=f"RACE{unique}A", account_type="CHECKING", currency="AZN"
        )
        receiver = accounts.create(
            customer_id=customer.id, account_number=f"RACE{unique}B", account_type="CHECKING", currency="AZN"
        )
        await setup_session.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = 200
        receiver.status = AccountStatus.ACTIVE
        receiver.balance = 0

        transactions = TransactionRepository(setup_session)
        transaction = transactions.create(
            sender_account_id=sender.id,
            receiver_account_id=receiver.id,
            amount=100,
            currency="AZN",
            exchange_rate_id=None,
            converted_amount=100,
        )
        await setup_session.flush()

        otp_code = generate_otp_code()
        confirmations = TransferConfirmationRepository(setup_session)
        from datetime import datetime, timedelta, timezone

        confirmations.create(
            transaction_id=transaction.id,
            otp_code_hash=hash_otp_code(otp_code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await setup_session.commit()

        sender_id, receiver_id, transaction_id, customer_id = (
            sender.id,
            receiver.id,
            transaction.id,
            customer.id,
        )

    # --- Race: two independent sessions confirm the same transaction at once ---
    async def _attempt_confirm():
        async with session_factory() as session:
            customers = CustomerRepository(session)
            customer = await customers.get_by_user_id(user.id)
            service = TransactionService(session)
            try:
                await service.confirm_transfer(customer, transaction_id, otp_code)
                return "success"
            except Exception as exc:  # noqa: BLE001 — we want to classify any failure
                return type(exc).__name__

    results = await asyncio.gather(_attempt_confirm(), _attempt_confirm(), return_exceptions=False)

    try:
        assert results.count("success") == 1, f"expected exactly one winner, got {results}"

        # Verify the money moved exactly once — no double-debit, no lost update.
        async with session_factory() as verify_session:
            accounts = AccountRepository(verify_session)
            final_sender = await accounts.get_by_id(sender_id)
            final_receiver = await accounts.get_by_id(receiver_id)
            assert final_sender.balance == 100
            assert final_receiver.balance == 100

            transactions = TransactionRepository(verify_session)
            final_transaction = await transactions.get_by_id(transaction_id)
            assert final_transaction.status == TransactionStatus.SUCCESS

            from app.modules.ledger_entries.repository import LedgerEntryRepository

            ledger_entries = await LedgerEntryRepository(verify_session).list_for_transaction(transaction_id)
            assert len(ledger_entries) == 2
    finally:
        # --- Manual cleanup since this test bypassed the rollback fixture ---
        async with session_factory() as cleanup_session:
            from sqlalchemy import delete

            from app.modules.accounts.models import Account
            from app.modules.audit_logs.models import AuditLog
            from app.modules.customers.models import Customer
            from app.modules.ledger_entries.models import LedgerEntry
            from app.modules.transactions.models import TransferConfirmation
            from app.modules.users.models import User

            await cleanup_session.execute(
                delete(LedgerEntry).where(LedgerEntry.transaction_id == transaction_id)
            )
            await cleanup_session.execute(
                delete(TransferConfirmation).where(TransferConfirmation.transaction_id == transaction_id)
            )
            await cleanup_session.execute(delete(Transaction).where(Transaction.id == transaction_id))
            await cleanup_session.execute(
                delete(Account).where(Account.id.in_([sender_id, receiver_id]))
            )
            await cleanup_session.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup_session.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
            await cleanup_session.execute(delete(User).where(User.id == user.id))
            await cleanup_session.commit()
        await engine.dispose()
