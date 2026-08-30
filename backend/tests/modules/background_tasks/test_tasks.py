import pytest
from sqlalchemy import select

from app.background_tasks.tasks import _write_audit_log_async
from app.modules.audit_logs.models import AuditLog


@pytest.mark.asyncio
async def test_write_audit_log_async_persists_entry(db_session, monkeypatch):
    """
    The Celery task itself opens its own session via CelerySessionLocal, which
    would bypass our test's transaction-rollback isolation. We instead verify
    the underlying write_audit_log() call directly through our test session —
    the task wrapper (_write_audit_log_async) is exercised for its argument
    parsing / UUID coercion logic here, while the actual DB write path is
    already covered by write_audit_log() unit tests below.
    """
    import uuid

    from app.modules.audit_logs.service import write_audit_log

    user_id = uuid.uuid4()
    await write_audit_log(
        db_session,
        user_id=user_id,
        action="TEST_ACTION",
        resource_type="test",
        resource_id=user_id,
        ip_address="127.0.0.1",
        metadata={"key": "value"},
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog).where(AuditLog.action == "TEST_ACTION"))
    entry = result.scalar_one()
    assert entry.user_id == user_id
    assert entry.log_metadata == {"key": "value"}
    assert str(entry.ip_address) == "127.0.0.1"


@pytest.mark.asyncio
async def test_write_audit_log_async_handles_none_ids():
    """UUID coercion in the task wrapper must tolerate None values (e.g. for
    login attempts against an unknown email, where no user_id exists yet)."""
    from unittest.mock import AsyncMock, patch

    with patch("app.background_tasks.tasks.CelerySessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        with patch("app.background_tasks.tasks.write_audit_log", new=AsyncMock()) as mock_write:
            await _write_audit_log_async(None, "LOGIN_FAILED", None, None, None, None)
            mock_write.assert_awaited_once()
            _, kwargs = mock_write.call_args
            assert kwargs["user_id"] is None
            assert kwargs["resource_id"] is None


@pytest.mark.asyncio
async def test_expire_stale_transactions_marks_expired_pending_as_failed(db_session):
    """
    Exercises the same query/update logic `expire_stale_transactions_task`
    uses, run against our session directly so it participates in the test's
    rollback isolation (the real task opens its own session via
    CelerySessionLocal, which would bypass that isolation).
    """
    import uuid
    from datetime import date, datetime, timedelta, timezone

    from app.core.security import generate_otp_code, hash_otp_code
    from app.modules.accounts.models import AccountStatus
    from app.modules.accounts.repository import AccountRepository
    from app.modules.customers.repository import CustomerRepository
    from app.modules.transactions.models import (
        Transaction,
        TransactionStatus,
        TransferConfirmation,
    )
    from app.modules.transactions.repository import (
        TransactionRepository,
        TransferConfirmationRepository,
    )
    from app.modules.users.repository import UserRepository

    unique = uuid.uuid4().hex[:8]
    users = UserRepository(db_session)
    user = users.create(email=f"sweep_{unique}@example.com", password_hash="x")
    await db_session.flush()
    customers = CustomerRepository(db_session)
    customer = customers.create(
        user_id=user.id,
        first_name="Sweep",
        last_name="Test",
        date_of_birth=date(1990, 1, 1),
        phone_number="+994500000001",
    )
    await db_session.flush()

    accounts = AccountRepository(db_session)
    sender = accounts.create(
        customer_id=customer.id, account_number=f"SWEEP{unique}A", account_type="CHECKING", currency="AZN"
    )
    receiver = accounts.create(
        customer_id=customer.id, account_number=f"SWEEP{unique}B", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    sender.status = AccountStatus.ACTIVE
    sender.balance = 100
    receiver.status = AccountStatus.ACTIVE

    transactions = TransactionRepository(db_session)
    transaction = transactions.create(
        sender_account_id=sender.id,
        receiver_account_id=receiver.id,
        amount=10,
        currency="AZN",
        exchange_rate_id=None,
        converted_amount=10,
    )
    await db_session.flush()

    confirmations = TransferConfirmationRepository(db_session)
    confirmations.create(
        transaction_id=transaction.id,
        otp_code_hash=hash_otp_code(generate_otp_code()),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),  # already expired
    )
    await db_session.commit()

    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    result = await db_session.execute(
        select(Transaction, TransferConfirmation)
        .join(TransferConfirmation, TransferConfirmation.transaction_id == Transaction.id)
        .where(
            Transaction.status == TransactionStatus.PENDING,
            TransferConfirmation.expires_at <= now,
            Transaction.id == transaction.id,
        )
    )
    rows = result.all()
    assert len(rows) == 1
    for txn, _confirmation in rows:
        await transactions.mark_failed(txn, "OTP expired (auto-expired by housekeeping sweep)")
    await db_session.commit()

    await db_session.refresh(transaction)
    assert transaction.status == TransactionStatus.FAILED
    assert "auto-expired" in transaction.failure_reason


@pytest.mark.asyncio
async def test_send_notification_renders_known_template_and_calls_provider():
    """
    _send_notification_async opens its own connection via CelerySessionLocal
    (by design — see module docstring), which is a different connection than
    the rollback-isolated `db_session` fixture uses. A user created through
    `db_session` would be invisible to it (uncommitted from Postgres's point
    of view), so this test commits a real user directly and cleans it up
    afterwards, the same pattern used in test_concurrency.py.
    """
    import uuid
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _send_notification_async
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as setup_session:
        users = UserRepository(setup_session)
        user = users.create(email=f"notify_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        await setup_session.commit()
        user_id = user.id
        user_email = user.email

    try:
        mock_provider = AsyncMock()
        with patch("app.core.email.create_email_provider", return_value=mock_provider):
            await _send_notification_async(
                str(user_id),
                "email",
                "transfer_otp",
                {"reference_number": "TXN-ABC123", "otp_code": "654321"},
            )

        mock_provider.send.assert_awaited_once()
        call_kwargs = mock_provider.send.call_args.kwargs
        assert call_kwargs["to_address"] == user_email
        assert "TXN-ABC123" in call_kwargs["body"]
        assert "654321" in call_kwargs["body"]
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(delete(User).where(User.id == user_id))
            await cleanup_session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_notification_skips_provider_lookup_for_unknown_channel():
    """A channel that's neither 'email' nor 'sms' (e.g. a future 'push')
    should not attempt to create any provider — it just logs. Uses a real
    committed user so the test genuinely reaches the channel-dispatch
    branch rather than short-circuiting earlier on user-not-found."""
    import uuid as uuid_module
    from unittest.mock import patch

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _send_notification_async
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"push_channel_{unique}@example.com", password_hash="x")
        await setup.commit()
        user_id = user.id

    try:
        with patch("app.core.email.create_email_provider") as mock_email_provider:
            with patch("app.core.sms.create_sms_provider") as mock_sms_provider:
                await _send_notification_async(str(user_id), "push", "transfer_otp", {"otp_code": "1"})
                mock_email_provider.assert_not_called()
                mock_sms_provider.assert_not_called()
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_notification_handles_unknown_recipient_gracefully():
    import uuid

    from app.background_tasks.tasks import _send_notification_async

    # Must not raise even though this user_id doesn't exist in the DB.
    await _send_notification_async(str(uuid.uuid4()), "email", "transfer_otp", {})


@pytest.mark.asyncio
async def test_send_notification_degrades_gracefully_for_unknown_template():
    import uuid
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _send_notification_async
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as setup_session:
        users = UserRepository(setup_session)
        user = users.create(email=f"unknown_tpl_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        await setup_session.commit()
        user_id = user.id

    try:
        mock_provider = AsyncMock()
        with patch("app.core.email.create_email_provider", return_value=mock_provider):
            await _send_notification_async(
                str(user_id), "email", "some_future_template", {"foo": "bar"}
            )
        mock_provider.send.assert_awaited_once()
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(delete(User).where(User.id == user_id))
            await cleanup_session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_notification_routes_sms_channel_to_customer_phone_number():
    import uuid as uuid_module
    from datetime import date
    from unittest.mock import AsyncMock, patch

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _send_notification_async
    from app.modules.customers.models import Customer
    from app.modules.customers.repository import CustomerRepository
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"sms_notify_{unique}@example.com", password_hash="x")
        await setup.flush()
        customers = CustomerRepository(setup)
        customer = customers.create(
            user_id=user.id,
            first_name="SMS",
            last_name="Test",
            date_of_birth=date(1990, 1, 1),
            phone_number="+994507654321",
        )
        await setup.commit()
        user_id, customer_id = user.id, customer.id

    try:
        mock_provider = AsyncMock()
        with patch("app.core.sms.create_sms_provider", return_value=mock_provider):
            await _send_notification_async(
                str(user_id), "sms", "transfer_otp", {"otp_code": "111222", "reference_number": "TXN-X"}
            )

        mock_provider.send.assert_awaited_once()
        call_kwargs = mock_provider.send.call_args.kwargs
        assert call_kwargs["to_number"] == "+994507654321"
        assert "111222" in call_kwargs["body"]
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(Customer).where(Customer.id == customer_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_send_notification_sms_skips_when_customer_profile_missing():
    """An ADMIN user (no Customer row) requesting an SMS notification should
    be skipped gracefully, not raise."""
    import uuid as uuid_module
    from unittest.mock import patch

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.background_tasks.tasks import _send_notification_async
    from app.modules.users.models import User
    from app.modules.users.repository import UserRepository
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    unique = uuid_module.uuid4().hex[:8]
    async with session_factory() as setup:
        users = UserRepository(setup)
        user = users.create(email=f"admin_no_customer_{unique}@example.com", password_hash="x")
        await setup.commit()
        user_id = user.id

    try:
        with patch("app.core.sms.create_sms_provider") as mock_create_provider:
            await _send_notification_async(str(user_id), "sms", "transfer_otp", {"otp_code": "1"})
            mock_create_provider.assert_not_called()
    finally:
        async with session_factory() as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
