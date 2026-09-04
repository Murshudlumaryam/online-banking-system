import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.auth.models import RefreshToken
    from app.modules.customers.models import Customer


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.CUSTOMER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Gates login, not registration itself — the account is created
    # immediately (see AuthService.register), but login is refused until
    # the registration OTP sent by email is confirmed (see
    # AuthService.confirm_registration). Existing rows from before this
    # field existed default to True at the database level (migration
    # 0013) so no one already registered gets locked out; new signups get
    # False explicitly in application code (see UserRepository.create).
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- TOTP-based two-factor authentication (Phase 7) ---
    # totp_secret is set (but totp_enabled stays False) as soon as the user
    # starts enrollment; it only becomes the "real" active secret once they
    # prove possession of it via /auth/2fa/enable. Stored **encrypted at
    # rest** (Fernet, see app/core/crypto.py) — a raw base32 TOTP secret is
    # ~32 chars, the encrypted token is ~140; sized generously for headroom.
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="user", uselist=False, lazy="selectin"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", lazy="noload"
    )
