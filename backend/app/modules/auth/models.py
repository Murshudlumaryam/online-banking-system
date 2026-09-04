import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.users.models import User


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class RegistrationConfirmation(UUIDPrimaryKeyMixin, Base):
    """
    One-to-one OTP challenge attached to a newly-registered user's email
    verification — deliberately the same shape as
    app.modules.transactions.models.TransferConfirmation (hash, expiry,
    attempts/max_attempts, verified_at, UNIQUE FK to the thing it
    confirms) rather than a generic reusable "OTP" table shared across
    every purpose. A UNIQUE constraint on user_id means a registration OTP
    can never be mistaken for or reused against any other user or any
    other flow (login's TOTP, a transfer's OTP) — that's a database
    constraint, not just application logic remembering to check a
    "purpose" column correctly.
    """

    __tablename__ = "registration_confirmations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    otp_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
