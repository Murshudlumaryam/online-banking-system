"""
Test fixtures.

Integration tests in this suite run against a real PostgreSQL instance —
Postgres-specific column types (UUID, JSONB, INET, native ENUM) are used
throughout the schema, so SQLite/mocks would give false confidence.

Point TEST_DATABASE_URL at a disposable database before running tests, e.g.
the `db` service from docker-compose.yml with a different database name:

    TEST_DATABASE_URL=postgresql+asyncpg://banking_user:banking_pass@localhost:5432/banking_test_db
    pytest

Each test runs inside a transaction that is rolled back afterwards, so tests
never leak state into one another and the database can be reused across runs.
"""
import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

# Must run before any `app.*` import — settings are cached via lru_cache, so
# whichever value is in the environment the first time get_settings() is
# called anywhere wins for the rest of the process. Tests use the in-memory
# rate limiter so the suite has no Redis dependency and no cross-test-run
# counter leakage.
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")

# A fixed, well-formed (but obviously not-secret) Fernet key so 2FA tests
# can encrypt/decrypt TOTP secrets without every developer having to
# generate and export one locally. Never reuse this value outside tests —
# see .env.production.example for how a real deployment generates its own.
os.environ.setdefault("ENCRYPTION_KEY", "qZ_JcB_hV7g9K00Ho6v5MGXR9Eu6JmfKYy1pxOOq8A4=")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import models_registry  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


async def register_and_confirm(client: AsyncClient, stub_background_tasks, payload: dict) -> dict:
    """
    Shared by every test that needs a real, logged-in-capable account
    without going through the full `registered_customer` fixture (e.g.
    tests that need a specific email/payload, or need the raw register
    response). Registers, extracts the registration OTP from the
    intercepted send_notification_task.delay(...) call (same mechanism as
    `registered_customer` — see that fixture's docstring for why not
    app.core.test_otp_store), and confirms it. Does NOT log in — callers
    that need a session still call POST /auth/login themselves afterward,
    same as before this helper existed.

    Returns the raw JSON body of the register response (so callers that
    need `id`/`customer` from it don't have to register again).
    """
    register = await client.post("/api/v1/auth/register", json=payload)
    if register.status_code != 201:
        return register.json()  # let the caller's own assertions surface the failure

    user_id = register.json()["id"]
    otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "registration_otp" and args[0] == user_id
    ]
    assert otp_calls, "expected a registration_otp notification to have been dispatched"
    otp_code = otp_calls[-1][3]["otp_code"]

    confirm = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code}
    )
    assert confirm.status_code == 204, f"registration confirm failed: {confirm.text}"
    return register.json()


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://banking_user:banking_pass@localhost:5432/banking_test_db",
)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """
    Creates all tables once per test session using a short-lived engine and
    event loop of its own (via asyncio.run), entirely independent of
    pytest-asyncio's per-test event loop. Mixing a pytest-asyncio-managed
    event loop with a session-scoped async fixture is a well-known source of
    "Future attached to a different loop" errors with asyncpg — this sidesteps
    the problem instead of fighting pytest-asyncio's loop-scope configuration.
    """

    async def _setup():
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_setup())
    yield

    async def _teardown():
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_teardown())


@pytest.fixture(autouse=True)
async def _dispose_global_engine_after_test():
    """
    Background-task helpers (_send_notification_async, _write_audit_log_async,
    etc.) deliberately use the module-level `app.db.session.AsyncSessionLocal`
    rather than the request-scoped `get_db` dependency, since that's exactly
    how they run in production (outside any HTTP request). But its
    connection pool persists across tests, while pytest-asyncio gives each
    test function a fresh event loop — a pooled asyncpg connection created
    in one test's loop cannot be reused in the next test's loop. Disposing
    the pool after every test forces fresh connections next time, at the
    cost of a bit of reconnect overhead.
    """
    yield
    import app.db.session as session_module

    await session_module.engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fresh engine + connection per test, bound to that test's own event loop.
    Standard SQLAlchemy "join a session into an external transaction" recipe:
    the outer transaction is rolled back at the end of every test regardless
    of how many times the code under test calls session.commit() — a
    SAVEPOINT is transparently restarted after each one.
    """
    from sqlalchemy import event

    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    connection = await engine.connect()
    outer_transaction = await connection.begin()

    session_factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    session = session_factory()

    await connection.begin_nested()  # SAVEPOINT

    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(autouse=True)
def stub_background_tasks(monkeypatch):
    """
    Background tasks (audit logging, notifications) are dispatched via Celery
    `.delay()`. Unit/integration tests should not require a running Redis
    broker, so we replace `.delay` with a no-op recorder. Task *logic* itself
    (write_audit_log, notification formatting) can and should be unit-tested
    separately by calling the underlying functions directly.
    """
    from app.background_tasks import tasks as bg_tasks

    calls: list[tuple[str, tuple]] = []

    def _fake_delay(task_name):
        def _inner(*args, **kwargs):
            calls.append((task_name, args))
            return None

        return _inner

    monkeypatch.setattr(bg_tasks.write_audit_log_task, "delay", _fake_delay("write_audit_log_task"))
    monkeypatch.setattr(bg_tasks.send_notification_task, "delay", _fake_delay("send_notification_task"))
    return calls


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient, db_session, unique_email: str) -> dict:
    """
    Creates an ADMIN-role user directly (registration always creates
    CUSTOMER-role users, so this bypasses that endpoint) and logs in through
    the real /auth/login flow to obtain a genuine JWT.
    """
    from app.core.security import hash_password
    from app.modules.users.models import UserRole
    from app.modules.users.repository import UserRepository

    admin_email = f"admin_{unique_email}"
    users = UserRepository(db_session)
    users.create(
        email=admin_email, password_hash=hash_password("AdminStrongPass1"), role=UserRole.ADMIN,
        email_verified=True,
    )
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login", json={"email": admin_email, "password": "AdminStrongPass1"}
    )
    tokens = login.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def registered_customer(
    client: AsyncClient, db_session, unique_email: str, stub_background_tasks
) -> dict:
    """
    Registers + confirms the registration OTP + logs in a fresh customer,
    returning tokens, headers, and the ORM Customer row (loaded in the
    same test-scoped session so it can be used to seed accounts/cards
    directly via repositories).

    Depends on stub_background_tasks (not app.core.test_otp_store) for the
    same reason tests/modules/transactions/test_transfer.py's OTP tests
    do: test_otp_store is gated behind ENVIRONMENT=test, which this suite
    deliberately does not set (see this file's module docstring on having
    no Redis dependency) — the code is instead read back from the
    intercepted send_notification_task.delay(...) call, which is how
    every other OTP flow in this test suite gets its code.
    """
    from datetime import date

    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    payload = {
        "email": unique_email,
        "password": "StrongPass1",
        "first_name": "Test",
        "last_name": "User",
        "date_of_birth": str(date(1993, 6, 15)),
        "phone_number": "+994551234567",
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
    }
    await client.post("/api/v1/auth/register", json=payload)

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()

    otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "registration_otp"
    ]
    assert otp_calls, "expected a registration_otp notification to have been dispatched"
    otp_code = otp_calls[-1][3]["otp_code"]

    confirm = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": str(user.id), "otp_code": otp_code}
    )
    assert confirm.status_code == 204, f"registration confirm failed: {confirm.text}"

    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    tokens = login.json()

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == unique_email.lower())
    )
    customer = result.scalar_one()

    return {
        "email": unique_email,
        "tokens": tokens,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        "customer": customer,
    }
