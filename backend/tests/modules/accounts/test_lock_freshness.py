"""
Direct check: does an EARLIER unlocked read of an account in a session,
followed by a LATER get_two_for_update() call for the same account in the
same session (exactly what confirm_transfer's real flow does —
_customer_owns_transaction reads the sender account unlocked, then
_execute_locked_transfer locks it later), correctly see changes committed
by another session in between? Or does SQLAlchemy's identity map silently
return the stale, pre-lock balance — the same class of bug just fixed for
TransactionRepository.get_for_update?
"""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.customers.repository import CustomerRepository
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_get_two_for_update_sees_fresh_balance_after_earlier_unlocked_read_in_same_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    unique = uuid.uuid4().hex[:10]

    async with session_factory() as setup:
        users = UserRepository(setup)
        customers = CustomerRepository(setup)
        accounts = AccountRepository(setup)

        user = users.create(email=f"staleness_{unique}@example.com", password_hash="x")
        await setup.flush()
        customer = customers.create(
            user_id=user.id, first_name="Stale", last_name="Check",
            date_of_birth=date(1990, 1, 1), phone_number="+994500000301",
        )
        await setup.flush()

        account = accounts.create(
            customer_id=customer.id, account_number=f"STALE{unique}", account_type="CHECKING", currency="AZN"
        )
        await setup.flush()
        account.status = AccountStatus.ACTIVE
        account.balance = 1000
        await setup.commit()
        account_id, customer_id, user_id = account.id, customer.id, user.id

    try:
        # Session A: read the account unlocked first (mirrors
        # _customer_owns_transaction's get_by_id call in the real flow).
        async with session_factory() as session_a:
            repo_a = AccountRepository(session_a)
            first_read = await repo_a.get_by_id(account_id)
            assert first_read.balance == 1000

            # Session B: a fully independent connection commits a balance
            # change in between — simulating a concurrent transfer.
            async with session_factory() as session_b:
                repo_b = AccountRepository(session_b)
                other_account_id = account_id  # reuse the same row for simplicity
                locked = await repo_b.get_two_for_update(other_account_id, other_account_id)
                acc = locked[other_account_id]
                acc.balance = 400  # simulate a debit having happened
                await session_b.commit()

            # Back on session A: lock the SAME account it already read
            # unlocked above. Must see 400 (the committed change), not the
            # stale 1000 cached in session A's identity map.
            locked_a = await repo_a.get_two_for_update(account_id, account_id)
            fresh_balance = locked_a[account_id].balance
            await session_a.commit()

            assert fresh_balance == 400, (
                f"CRITICAL: get_two_for_update returned a stale balance ({fresh_balance}) "
                f"instead of the freshly-committed value (400) — the same identity-map "
                f"staleness bug fixed for TransactionRepository.get_for_update is also "
                f"present here."
            )
    finally:
        async with session_factory() as cleanup:
            from sqlalchemy import delete

            from app.modules.accounts.models import Account
            from app.modules.customers.models import Customer
            from app.modules.users.models import User

            await cleanup.execute(delete(Account).where(Account.id == account_id))
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
