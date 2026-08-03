"""
The exact regression test requested during a production-readiness review:
two simultaneous OTP confirmation requests for the SAME transaction, sent
through the full `TransactionService.confirm_transfer()` path (the real
method the HTTP endpoint calls) — not a lower-level bypass. Uses an
asyncio.Barrier to force genuine simultaneity; see
test_double_confirmation_vulnerability.py's module docstring for why
asyncio.gather alone is not sufficient to reliably reproduce this race.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import generate_otp_code, hash_otp_code
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.repository import CustomerRepository
from app.modules.ledger_entries.models import LedgerEntry
from app.modules.transactions.models import TransactionStatus
from app.modules.transactions.repository import (
    TransactionRepository,
    TransferConfirmationRepository,
)
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_two_simultaneous_otp_confirm_requests_same_transaction():
    """Two clients (e.g. a slow network causing the customer to tap
    'Confirm' twice, or a naive retry) send POST .../confirm with the SAME
    valid OTP code for the SAME transaction at the same instant. Exactly
    one must succeed; the transaction must end up SUCCESS (not PENDING,
    not double-applied); ledger entries must number exactly two."""
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    unique = uuid.uuid4().hex[:10]

    async with session_factory() as setup:
        users = UserRepository(setup)
        customers = CustomerRepository(setup)
        accounts = AccountRepository(setup)

        user = users.create(email=f"dual_otp_{unique}@example.com", password_hash="x")
        await setup.flush()
        customer = customers.create(
            user_id=user.id, first_name="Dual", last_name="Otp",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000401",
        )
        await setup.flush()

        sender = accounts.create(
            customer_id=customer.id, account_number=f"DOTP{unique}A", account_type="CHECKING", currency="AZN"
        )
        receiver = accounts.create(
            customer_id=customer.id, account_number=f"DOTP{unique}B", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = 5_000  # abundant — must not allow a double-debit even so
        receiver.status = AccountStatus.ACTIVE
        receiver.balance = 0

        transactions_repo = TransactionRepository(setup)
        confirmations_repo = TransferConfirmationRepository(setup)

        txn = transactions_repo.create(
            sender_account_id=sender.id, receiver_account_id=receiver.id,
            amount=250, currency="AZN", exchange_rate_id=None, converted_amount=250,
        )
        await setup.flush()

        otp_code = generate_otp_code()
        confirmations_repo.create(
            transaction_id=txn.id, otp_code_hash=hash_otp_code(otp_code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await setup.commit()

        sender_id, receiver_id, txn_id, customer_id, user_id = (
            sender.id, receiver.id, txn.id, customer.id, user.id,
        )

    barrier = asyncio.Barrier(2)

    async def _confirm_request():
        async with session_factory() as session:
            from app.modules.transactions.service import TransactionService

            cust = await CustomerRepository(session).get_by_user_id(user_id)
            service = TransactionService(session)

            # Force both requests to have independently loaded the
            # transaction as PENDING before either is allowed to proceed
            # into confirm_transfer — this is what actually makes the race
            # reproducible instead of leaving it to scheduling luck.
            await service._get_owned_pending_transaction(cust, txn_id)
            await barrier.wait()

            try:
                await service.confirm_transfer(cust, txn_id, otp_code)
                return "success"
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__

    results = await asyncio.gather(_confirm_request(), _confirm_request())

    try:
        print(f"\nRESULTS: {results}")
        assert results.count("success") == 1, f"expected exactly one winner, got: {results}"

        async with session_factory() as verify:
            accounts_repo = AccountRepository(verify)
            final_sender = await accounts_repo.get_by_id(sender_id)
            final_receiver = await accounts_repo.get_by_id(receiver_id)
            assert final_sender.balance == 4750, f"sender balance is {final_sender.balance}, expected 4750"
            assert final_receiver.balance == 250, f"receiver balance is {final_receiver.balance}, expected 250"

            transactions_repo = TransactionRepository(verify)
            final_txn = await transactions_repo.get_by_id(txn_id)
            assert final_txn.status == TransactionStatus.SUCCESS
            assert final_txn.otp_verified is True

            ledger_result = await verify.execute(
                select(LedgerEntry).where(LedgerEntry.transaction_id == txn_id)
            )
            ledger_rows = ledger_result.scalars().all()
            assert len(ledger_rows) == 2, f"expected exactly 2 ledger rows, got {len(ledger_rows)}"
    finally:
        async with session_factory() as cleanup:
            from sqlalchemy import delete

            from app.modules.accounts.models import Account
            from app.modules.audit_logs.models import AuditLog
            from app.modules.customers.models import Customer
            from app.modules.transactions.models import Transaction, TransferConfirmation
            from app.modules.users.models import User

            await cleanup.execute(delete(LedgerEntry).where(LedgerEntry.transaction_id == txn_id))
            await cleanup.execute(
                delete(TransferConfirmation).where(TransferConfirmation.transaction_id == txn_id)
            )
            await cleanup.execute(delete(Transaction).where(Transaction.id == txn_id))
            await cleanup.execute(delete(Account).where(Account.id.in_([sender_id, receiver_id])))
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
