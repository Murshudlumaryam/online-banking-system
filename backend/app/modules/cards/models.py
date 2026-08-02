import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.accounts.models import Account


class CardStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


class Card(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cards"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    masked_card_number: Mapped[str] = mapped_column(String(19), nullable=False)
    card_type: Mapped[str] = mapped_column(String(16), nullable=False, default="DEBIT")
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CardStatus] = mapped_column(
        Enum(CardStatus, name="card_status", native_enum=True),
        nullable=False,
        default=CardStatus.ACTIVE,
    )
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship("Account")

    @staticmethod
    def mask(card_number: str) -> str:
        """4111111111111111 -> 4111 **** **** 1111"""
        digits = "".join(ch for ch in card_number if ch.isdigit())
        if len(digits) < 8:
            return "**** **** **** ****"
        return f"{digits[:4]} **** **** {digits[-4:]}"
