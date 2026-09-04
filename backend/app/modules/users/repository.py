import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return await self.get_by_email(email) is not None

    def create(
        self, *, email: str, password_hash: str, role: UserRole = UserRole.CUSTOMER, email_verified: bool = False
    ) -> User:
        user = User(email=email.lower(), password_hash=password_hash, role=role, email_verified=email_verified)
        self._session.add(user)
        return user

    async def mark_login(self, user: User) -> None:
        user.last_login_at = datetime.now(timezone.utc)
        self._session.add(user)

    async def save(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()
