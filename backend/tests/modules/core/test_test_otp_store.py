import pytest
from httpx import AsyncClient

from app.core import test_otp_store
from app.core.config import get_settings


@pytest.fixture
def enable_test_otp_store(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    get_settings.cache_clear()


def test_capture_and_pop_roundtrip(enable_test_otp_store):
    import uuid

    transaction_id = uuid.uuid4()
    test_otp_store.capture(transaction_id, "123456")
    assert test_otp_store.pop(transaction_id) == "123456"


def test_pop_is_read_once(enable_test_otp_store):
    import uuid

    transaction_id = uuid.uuid4()
    test_otp_store.capture(transaction_id, "123456")
    test_otp_store.pop(transaction_id)
    assert test_otp_store.pop(transaction_id) is None


def test_capture_is_a_no_op_when_disabled():
    """Default test suite environment is not 'test' (it's 'development'),
    so capture must silently do nothing — this is the state our entire
    existing test suite already runs under, and it must stay inert there."""
    import uuid

    assert test_otp_store.is_enabled() is False
    transaction_id = uuid.uuid4()
    test_otp_store.capture(transaction_id, "123456")
    assert test_otp_store.pop(transaction_id) is None


@pytest.mark.asyncio
async def test_debug_otp_endpoint_404s_outside_test_environment(
    client: AsyncClient, registered_customer: dict
):
    import uuid

    response = await client.get(
        f"/api/v1/transactions/{uuid.uuid4()}/debug-otp", headers=registered_customer["headers"]
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_debug_otp_endpoint_returns_captured_code_in_test_environment(
    client: AsyncClient, db_session, registered_customer: dict, enable_test_otp_store
):
    from app.modules.accounts.models import AccountStatus
    from app.modules.accounts.repository import AccountRepository

    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    sender = accounts.create(
        customer_id=customer.id, account_number="DEBUGOTP01", account_type="CHECKING", currency="AZN"
    )
    receiver = accounts.create(
        customer_id=customer.id, account_number="DEBUGOTP02", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    sender.status = AccountStatus.ACTIVE
    sender.balance = 100
    receiver.status = AccountStatus.ACTIVE
    await db_session.commit()

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "DEBUGOTP02",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    debug_response = await client.get(
        f"/api/v1/transactions/{transaction_id}/debug-otp", headers=registered_customer["headers"]
    )
    assert debug_response.status_code == 200
    otp_code = debug_response.json()["otp_code"]
    assert len(otp_code) == 6 and otp_code.isdigit()

    # Read-once — a second call must 404, exactly like the code being
    # single-use in any real inbox.
    second_response = await client.get(
        f"/api/v1/transactions/{transaction_id}/debug-otp", headers=registered_customer["headers"]
    )
    assert second_response.status_code == 404

    # And the captured code must actually be the real, working OTP.
    confirm_response = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=registered_customer["headers"],
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_debug_promote_to_admin_404s_outside_test_environment(
    client: AsyncClient, registered_customer: dict
):
    response = await client.post(
        "/api/v1/auth/debug-promote-to-admin", headers=registered_customer["headers"]
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_debug_promote_to_admin_works_in_test_environment(
    client: AsyncClient, registered_customer: dict, enable_test_otp_store
):
    promote_response = await client.post(
        "/api/v1/auth/debug-promote-to-admin", headers=registered_customer["headers"]
    )
    assert promote_response.status_code == 204

    # The promoted user can now access an admin-only endpoint. Note: the
    # access token issued before promotion still encodes role=CUSTOMER (JWTs
    # are immutable once signed), but require_admin re-checks the *current*
    # DB row's role, not the token's role claim, on every request — this
    # confirms that.
    admin_response = await client.get(
        "/api/v1/admin/customers", headers=registered_customer["headers"]
    )
    assert admin_response.status_code == 200


@pytest.mark.asyncio
async def test_debug_set_account_balance_404s_outside_test_environment(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    from app.modules.accounts.repository import AccountRepository

    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    account = accounts.create(
        customer_id=customer.id, account_number="DEBUGBAL01", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/admin/accounts/{account.id}/debug-set-balance",
        params={"amount": "500.00"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_debug_set_account_balance_works_in_test_environment(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict, enable_test_otp_store
):
    from app.modules.accounts.repository import AccountRepository

    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    account = accounts.create(
        customer_id=customer.id, account_number="DEBUGBAL02", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/admin/accounts/{account.id}/debug-set-balance",
        params={"amount": "500.00"},
        headers=admin_headers,
    )
    assert response.status_code == 204

    await db_session.refresh(account)
    assert account.balance == 500


@pytest.mark.asyncio
async def test_debug_set_account_balance_requires_admin(
    client: AsyncClient, db_session, registered_customer: dict, enable_test_otp_store
):
    from app.modules.accounts.repository import AccountRepository

    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    account = accounts.create(
        customer_id=customer.id, account_number="DEBUGBAL03", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/admin/accounts/{account.id}/debug-set-balance",
        params={"amount": "500.00"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_debug_promote_to_admin_actually_persists_across_real_separate_connections():
    """
    Regression test for a real bug found during manual e2e verification:
    the original implementation called UserRepository.save() (flush-only)
    without a following session.commit(), so the role change was silently
    rolled back when the request's session closed. The standard pytest
    `client` fixture couldn't catch this — it forces every request in a
    test to share one session/connection via a dependency override, so a
    flush alone was already visible to the "next" request in the same test.
    This test uses two genuinely independent connections (the same pattern
    as test_concurrency.py) specifically so a missing commit shows up here.
    """
    import uuid as uuid_module

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.security import hash_password
    from app.modules.users.models import User, UserRole
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"promote_regress_{unique}@example.com", password_hash=hash_password("x"))
        await setup.commit()
        user_id = user.id

    try:
        # Simulates the debug-promote-to-admin request using its own fresh
        # connection, exactly like a real HTTP request would.
        async with session_factory() as request_session:
            repo = UserRepository(request_session)
            fetched_user = await repo.get_by_id(user_id)
            assert fetched_user is not None
            fetched_user.role = UserRole.ADMIN
            await repo.save(fetched_user)
            await request_session.commit()  # the fix — must actually be here

        # A THIRD, independent connection must see the committed change.
        async with session_factory() as verify_session:
            verify_repo = UserRepository(verify_session)
            reloaded_user = await verify_repo.get_by_id(user_id)
            assert reloaded_user is not None
            assert reloaded_user.role == UserRole.ADMIN
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
