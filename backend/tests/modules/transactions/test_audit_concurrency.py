"""
Audit-driven test (not part of the original test suite): the existing
test_concurrent_confirm_cannot_double_spend proves that confirming the SAME
pending transaction twice concurrently cannot double-spend. This is a
narrower scenario than "two separate transfer requests fired at the same
time" — e.g. a user double-clicking 'Send' on two different transfers, or
initiating two transfers from two devices before either completes.

This test creates TWO INDEPENDENT transactions (separate transaction rows,
separate OTP challenges, separate receivers) from the SAME sender account
with a balance that can only cover ONE of them, and confirms both
concurrently through the full service-layer initiate+confirm path used by
the real HTTP endpoints. Correct behavior: exactly one succeeds, the other
fails with InsufficientBalanceError (discovered under lock, not from a
stale pre-lock read), and the final sender balance is never negative.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import InsufficientBalanceError
from app.core.security import generate_otp_code, hash_otp_code
from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.repository import CustomerRepository
from app.modules.transactions.models import TransactionStatus
from app.modules.transactions.repository import (
    TransactionRepository,
    TransferConfirmationRepository,
)
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_two_separate_transfers_from_same_sender_cannot_jointly_overdraw():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid.uuid4().hex[:10]

    async with session_factory() as setup:
        users = UserRepository(setup)
        customers = CustomerRepository(setup)
        accounts = AccountRepository(setup)

        user = users.create(email=f"audit_race_{unique}@example.com", password_hash="x")
        await setup.flush()
        customer = customers.create(
            user_id=user.id,
            first_name="Audit",
            last_name="Race",
            date_of_birth=date(1990, 1, 1),
            phone_number="+994500000111",
        )
        await setup.flush()

        sender = accounts.create(
            customer_id=customer.id, account_number=f"AUDR{unique}A", account_type="CHECKING", currency="AZN"
        )
        receiver_a = accounts.create(
            customer_id=customer.id, account_number=f"AUDR{unique}B", account_type="CHECKING", currency="AZN"
        )
        receiver_b = accounts.create(
            customer_id=customer.id, account_number=f"AUDR{unique}C", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = 100  # exactly enough for ONE of the two 100 AZN transfers below
        receiver_a.status = AccountStatus.ACTIVE
        receiver_b.status = AccountStatus.ACTIVE

        transactions_repo = TransactionRepository(setup)
        confirmations_repo = TransferConfirmationRepository(setup)

        txn_a = transactions_repo.create(
            sender_account_id=sender.id, receiver_account_id=receiver_a.id,
            amount=100, currency="AZN", exchange_rate_id=None, converted_amount=100,
        )
        txn_b = transactions_repo.create(
            sender_account_id=sender.id, receiver_account_id=receiver_b.id,
            amount=100, currency="AZN", exchange_rate_id=None, converted_amount=100,
        )
        await setup.flush()

        otp_a = generate_otp_code()
        otp_b = generate_otp_code()
        confirmations_repo.create(
            transaction_id=txn_a.id, otp_code_hash=hash_otp_code(otp_a),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        confirmations_repo.create(
            transaction_id=txn_b.id, otp_code_hash=hash_otp_code(otp_b),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await setup.commit()

        sender_id, receiver_a_id, receiver_b_id = sender.id, receiver_a.id, receiver_b.id
        txn_a_id, txn_b_id, customer_id, user_id = txn_a.id, txn_b.id, customer.id, user.id

    async def _confirm(transaction_id, otp_code):
        async with session_factory() as session:
            from app.modules.transactions.service import TransactionService

            customers = CustomerRepository(session)
            cust = await customers.get_by_user_id(user_id)
            service = TransactionService(session)
            try:
                await service.confirm_transfer(cust, transaction_id, otp_code)
                return "success"
            except InsufficientBalanceError:
                return "insufficient_balance"
            except Exception as exc:  # noqa: BLE001
                import traceback
                return f"unexpected:{type(exc).__name__}:{exc}\n{traceback.format_exc()}"

    results = await asyncio.gather(_confirm(txn_a_id, otp_a), _confirm(txn_b_id, otp_b))

    try:
        # The critical assertion: NOT both can succeed when the balance only
        # covers one. If this fails, the app can be double-spent.
        assert results.count("success") == 1, (
            f"CRITICAL: expected exactly 1 success out of 2 concurrent transfers "
            f"sharing a balance that only covers one, got: {results}"
        )
        assert "insufficient_balance" in results, f"expected the loser to fail cleanly, got: {results}"

        async with session_factory() as verify:
            accounts = AccountRepository(verify)
            final_sender = await accounts.get_by_id(sender_id)
            # The sender's balance must never go negative, and must reflect
            # exactly one 100 AZN debit, not zero (both failed) or -100 (both succeeded).
            assert final_sender.balance == 0, f"CRITICAL: sender balance is {final_sender.balance}, expected 0"
            assert final_sender.balance >= 0, "CRITICAL: sender balance went negative — overdraft occurred"

            transactions_repo = TransactionRepository(verify)
            final_a = await transactions_repo.get_by_id(txn_a_id)
            final_b = await transactions_repo.get_by_id(txn_b_id)
            statuses = {final_a.status, final_b.status}
            assert statuses == {TransactionStatus.SUCCESS, TransactionStatus.FAILED}, (
                f"expected one SUCCESS and one FAILED, got A={final_a.status}, B={final_b.status}"
            )
    finally:
        async with session_factory() as cleanup:
            from sqlalchemy import delete

            from app.modules.accounts.models import Account
            from app.modules.audit_logs.models import AuditLog
            from app.modules.customers.models import Customer
            from app.modules.ledger_entries.models import LedgerEntry
            from app.modules.transactions.models import Transaction, TransferConfirmation
            from app.modules.users.models import User

            await cleanup.execute(
                delete(LedgerEntry).where(LedgerEntry.transaction_id.in_([txn_a_id, txn_b_id]))
            )
            await cleanup.execute(
                delete(TransferConfirmation).where(
                    TransferConfirmation.transaction_id.in_([txn_a_id, txn_b_id])
                )
            )
            await cleanup.execute(delete(Transaction).where(Transaction.id.in_([txn_a_id, txn_b_id])))
            await cleanup.execute(
                delete(Account).where(Account.id.in_([sender_id, receiver_a_id, receiver_b_id]))
            )
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_ten_concurrent_transfers_only_correct_number_succeed():
    """More aggressive: 10 concurrent transfers of 30 AZN each from an
    account with a 100 AZN balance. Exactly 3 can succeed (90 AZN), the
    other 7 must fail — never more than the balance allows."""
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid.uuid4().hex[:10]
    N = 10
    AMOUNT = 30
    STARTING_BALANCE = 100

    async with session_factory() as setup:
        users = UserRepository(setup)
        customers = CustomerRepository(setup)
        accounts = AccountRepository(setup)

        user = users.create(email=f"audit_race10_{unique}@example.com", password_hash="x")
        await setup.flush()
        customer = customers.create(
            user_id=user.id, first_name="Audit", last_name="Ten",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000112",
        )
        await setup.flush()

        sender = accounts.create(
            customer_id=customer.id, account_number=f"AUD10{unique}A", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        sender.status = AccountStatus.ACTIVE
        sender.balance = STARTING_BALANCE

        receivers = []
        for i in range(N):
            r = accounts.create(
                customer_id=customer.id, account_number=f"AUD10{unique}R{i}",
                account_type="CHECKING", currency="AZN",
            )
            receivers.append(r)
        await setup.flush()
        for r in receivers:
            r.status = AccountStatus.ACTIVE

        transactions_repo = TransactionRepository(setup)
        confirmations_repo = TransferConfirmationRepository(setup)

        txns = []
        otps = []
        for r in receivers:
            txn = transactions_repo.create(
                sender_account_id=sender.id, receiver_account_id=r.id,
                amount=AMOUNT, currency="AZN", exchange_rate_id=None, converted_amount=AMOUNT,
            )
            txns.append(txn)
        await setup.flush()

        for txn in txns:
            otp = generate_otp_code()
            otps.append(otp)
            confirmations_repo.create(
                transaction_id=txn.id, otp_code_hash=hash_otp_code(otp),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        await setup.commit()

        sender_id = sender.id
        receiver_ids = [r.id for r in receivers]
        txn_ids = [t.id for t in txns]
        customer_id, user_id = customer.id, user.id

    async def _confirm(transaction_id, otp_code):
        async with session_factory() as session:
            from app.core.exceptions import InsufficientBalanceError
            from app.modules.transactions.service import TransactionService

            customers = CustomerRepository(session)
            cust = await customers.get_by_user_id(user_id)
            service = TransactionService(session)
            try:
                await service.confirm_transfer(cust, transaction_id, otp_code)
                return "success"
            except InsufficientBalanceError:
                return "insufficient_balance"
            except Exception as exc:  # noqa: BLE001
                import traceback
                return f"unexpected:{type(exc).__name__}:{exc}\n{traceback.format_exc()}"

    results = await asyncio.gather(*[_confirm(tid, otp) for tid, otp in zip(txn_ids, otps)])

    try:
        success_count = results.count("success")
        expected_max_successes = STARTING_BALANCE // AMOUNT  # 3
        assert success_count == expected_max_successes, (
            f"CRITICAL: expected exactly {expected_max_successes} successes out of "
            f"{N} concurrent {AMOUNT}-AZN transfers from a {STARTING_BALANCE}-AZN balance, "
            f"got {success_count}. Results: {results}"
        )

        async with session_factory() as verify:
            accounts = AccountRepository(verify)
            final_sender = await accounts.get_by_id(sender_id)
            expected_balance = STARTING_BALANCE - (success_count * AMOUNT)
            assert final_sender.balance == expected_balance
            assert final_sender.balance >= 0, "CRITICAL: sender balance went negative — overdraft occurred"
    finally:
        async with session_factory() as cleanup:
            from sqlalchemy import delete

            from app.modules.accounts.models import Account
            from app.modules.audit_logs.models import AuditLog
            from app.modules.customers.models import Customer
            from app.modules.ledger_entries.models import LedgerEntry
            from app.modules.transactions.models import Transaction, TransferConfirmation
            from app.modules.users.models import User

            await cleanup.execute(delete(LedgerEntry).where(LedgerEntry.transaction_id.in_(txn_ids)))
            await cleanup.execute(
                delete(TransferConfirmation).where(TransferConfirmation.transaction_id.in_(txn_ids))
            )
            await cleanup.execute(delete(Transaction).where(Transaction.id.in_(txn_ids)))
            await cleanup.execute(
                delete(Account).where(Account.id.in_([sender_id, *receiver_ids]))
            )
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
