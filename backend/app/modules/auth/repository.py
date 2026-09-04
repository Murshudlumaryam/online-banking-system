import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken, RegistrationConfirmation


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        return token

    async def revoke(self, token: RefreshToken, *, replaced_by: RefreshToken | None = None) -> None:
        token.revoked_at = datetime.now(timezone.utc)
        if replaced_by is not None:
            token.replaced_by_token_id = replaced_by.id
        self._session.add(token)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(timezone.utc)
        for token in result.scalars().all():
            token.revoked_at = now
            self._session.add(token)

    @staticmethod
    def is_valid(token: RefreshToken) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return token.revoked_at is None and expires_at > now


class RegistrationConfirmationRepository:
    """Mirrors app.modules.transactions.repository.TransferConfirmationRepository
    exactly — same hash/expiry/attempts/reissue shape, just keyed by
    user_id instead of transaction_id. See RegistrationConfirmation's
    model docstring for why this isn't a shared generic OTP table."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> RegistrationConfirmation | None:
        result = await self._session.execute(
            select(RegistrationConfirmation).where(RegistrationConfirmation.user_id == user_id)
        )
        return result.scalar_one_or_none()

    def create(
        self, *, user_id: uuid.UUID, otp_code_hash: str, expires_at: datetime
    ) -> RegistrationConfirmation:
        confirmation = RegistrationConfirmation(
            user_id=user_id, otp_code_hash=otp_code_hash, expires_at=expires_at
        )
        self._session.add(confirmation)
        return confirmation

    async def register_failed_attempt(self, confirmation: RegistrationConfirmation) -> None:
        confirmation.attempts += 1
        self._session.add(confirmation)

    async def reissue(
        self, confirmation: RegistrationConfirmation, *, otp_code_hash: str, expires_at: datetime
    ) -> None:
        confirmation.otp_code_hash = otp_code_hash
        confirmation.expires_at = expires_at
        confirmation.attempts = 0
        self._session.add(confirmation)

    async def mark_verified(self, confirmation: RegistrationConfirmation) -> None:
        confirmation.verified_at = datetime.now(timezone.utc)
        self._session.add(confirmation)

    @staticmethod
    def is_expired(confirmation: RegistrationConfirmation) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= now

    @staticmethod
    def attempts_exhausted(confirmation: RegistrationConfirmation) -> bool:
        return confirmation.attempts >= confirmation.max_attempts
