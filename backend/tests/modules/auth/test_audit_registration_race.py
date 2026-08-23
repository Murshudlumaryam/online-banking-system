"""
Audit-driven test: users.email has a DB-level UNIQUE constraint, but
AuthService.register() only pre-checks email_exists() in Python before
inserting — a classic TOCTOU race. Two concurrent registrations with the
same email could both pass the pre-check, then one hits the DB constraint.
Does that surface as a clean 409 (already registered) or an ugly 500?
"""
import asyncio
import uuid as uuid_module

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import TEST_DATABASE_URL


@pytest.mark.asyncio
async def test_concurrent_duplicate_registration_is_handled_gracefully():
    from datetime import date

    from app.modules.auth.schemas import RegisterCustomerRequest
    from app.modules.auth.service import AuthService

    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    email = f"race_register_{uuid_module.uuid4().hex[:10]}@example.com"
    payload = RegisterCustomerRequest(
        email=email,
        password="StrongPass1",
        first_name="Race",
        last_name="Register",
        date_of_birth=date(1990, 1, 1),
        phone_number="+994500000222",
        national_id=f"TEST{uuid_module.uuid4().hex[:12].upper()}",
    )
    payload_b = RegisterCustomerRequest(
        email=email,  # SAME email — this is the race
        password="StrongPass1",
        first_name="Race",
        last_name="RegisterB",
        date_of_birth=date(1990, 1, 1),
        phone_number="+994500000223",
        national_id=f"TEST{uuid_module.uuid4().hex[:12].upper()}",
    )

    async def _register(p):
        async with session_factory() as session:
            from app.core.exceptions import ConflictError

            service = AuthService(session)
            try:
                await service.register(p, ip_address=None)
                return "success"
            except ConflictError:
                return "clean_conflict_error"
            except Exception as exc:  # noqa: BLE001
                return f"unexpected:{type(exc).__name__}:{exc}"

    results = await asyncio.gather(_register(payload), _register(payload_b))

    try:
        assert results.count("success") == 1, f"expected exactly one winner, got: {results}"
        assert "clean_conflict_error" in results, (
            f"CRITICAL: the losing concurrent registration must raise a clean domain "
            f"error (ConflictError -> HTTP 409), not leak a raw DB exception as a 500. "
            f"Got: {results}"
        )
    finally:
        async with session_factory() as cleanup:
            from sqlalchemy import delete

            from app.modules.audit_logs.models import AuditLog
            from app.modules.customers.models import Customer
            from app.modules.users.models import User

            result = await cleanup.execute(sqlalchemy.select(User).where(User.email == email.lower()))
            users = result.scalars().all()
            for u in users:
                await cleanup.execute(delete(Customer).where(Customer.user_id == u.id))
                await cleanup.execute(delete(AuditLog).where(AuditLog.user_id == u.id))
            await cleanup.execute(delete(User).where(User.email == email.lower()))
            await cleanup.commit()
        await engine.dispose()
