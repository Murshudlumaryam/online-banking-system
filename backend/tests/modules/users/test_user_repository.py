import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.users.repository import UserRepository


@pytest.mark.asyncio
async def test_create_and_get_by_email(db_session: AsyncSession, unique_email: str):
    repo = UserRepository(db_session)
    repo.create(email=unique_email, password_hash=hash_password("StrongPass1"))
    await db_session.flush()

    found = await repo.get_by_email(unique_email)
    assert found is not None
    assert found.email == unique_email.lower()


@pytest.mark.asyncio
async def test_email_exists_is_case_insensitive(db_session: AsyncSession, unique_email: str):
    repo = UserRepository(db_session)
    repo.create(email=unique_email.lower(), password_hash=hash_password("StrongPass1"))
    await db_session.flush()

    assert await repo.email_exists(unique_email.upper()) is True


@pytest.mark.asyncio
async def test_get_by_email_returns_none_for_unknown_email(db_session: AsyncSession):
    repo = UserRepository(db_session)
    assert await repo.get_by_email("does-not-exist@example.com") is None
