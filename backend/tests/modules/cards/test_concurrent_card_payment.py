"""
Concurrency check for card payments: two concurrent payments against the
same card/account, together exceeding its balance, must not both succeed.
Same asyncio.Barrier technique as
tests/modules/transactions/test_concurrent_withdrawal.py — asyncio.gather
alone does not reliably force two coroutines to contend for a lock at the
same instant.
"""
import asyncio
import uuid
from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.accounts.models import Account, AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.audit_logs.models import AuditLog
from app.modules.cards.models import Card
from app.modules.cards.repository import CardRepository, generate_synthetic_pan
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.ledger_entries.models import LedgerEntry
from app.modules.transactions.models import Transaction
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_concurrent_card_payments_cannot_jointly_overdraw_account():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    unique = uuid.uuid4().hex[:10]

    async with session_factory() as setup:
        users = UserRepository(setup)
        customers = CustomerRepository(setup)
        accounts = AccountRepository(setup)
        cards = CardRepository(setup)

        user = users.create(email=f"concurrent_pay_{unique}@example.com", password_hash="x")
        await setup.flush()
        customer = customers.create(
            user_id=user.id, first_name="Concurrent", last_name="Pay",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000701",
            national_id=f"CPY{unique.upper()}",
        )
        await setup.flush()

        account = accounts.create(
            customer_id=customer.id, account_number=f"CPAY{unique}", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        account.status = AccountStatus.ACTIVE
        account.balance = 100  # exactly enough for ONE of two 100 AZN payments

        card = cards.create(
            account_id=account.id, raw_card_number=generate_synthetic_pan(),
            card_type="DEBIT", expiry_date=date(2030, 1, 1),
        )
        await setup.commit()

        account_id, card_id, customer_id, user_id = account.id, card.id, customer.id, user.id

    barrier = asyncio.Barrier(2)

    async def _pay():
        async with session_factory() as session:
            from app.core.exceptions import ConflictError
            from app.modules.cards.service import CardService
            from app.modules.customers.repository import CustomerRepository as CustRepo

            cust = await CustRepo(session).get_by_user_id(user_id)
            await barrier.wait()
            service = CardService(session)
            try:
                await service.pay_with_card(
                    cust, card_id, amount=100, currency="AZN", merchant_name="Concurrent Test Merchant",
                )
                return "success"
            except ConflictError as exc:
                return "insufficient_balance" if "balance" in str(exc).lower() else f"conflict:{exc}"
            except Exception as exc:  # noqa: BLE001
                return f"unexpected:{type(exc).__name__}"

    results = await asyncio.gather(_pay(), _pay())

    try:
        assert results.count("success") == 1, f"expected exactly one winner, got: {results}"
        assert "insufficient_balance" in results, f"expected the loser to fail cleanly, got: {results}"

        async with session_factory() as verify:
            accounts_repo = AccountRepository(verify)
            final_account = await accounts_repo.get_by_id(account_id)
            assert final_account.balance == 0, f"balance is {final_account.balance}, expected 0"
            assert final_account.balance >= 0, "CRITICAL: account went negative"
    finally:
        async with session_factory() as cleanup:
            result = await cleanup.execute(
                select(Transaction.id).where(Transaction.sender_account_id == account_id)
            )
            txn_ids = [row[0] for row in result.all()]
            if txn_ids:
                await cleanup.execute(delete(LedgerEntry).where(LedgerEntry.transaction_id.in_(txn_ids)))
                await cleanup.execute(delete(Transaction).where(Transaction.id.in_(txn_ids)))
            await cleanup.execute(delete(Card).where(Card.id == card_id))
            await cleanup.execute(delete(Account).where(Account.id == account_id))
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
