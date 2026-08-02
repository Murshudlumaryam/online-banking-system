import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BeneficiaryStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


class Beneficiary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beneficiaries"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    beneficiary_account_number: Mapped[str] = mapped_column(String(34), nullable=False)
    beneficiary_name: Mapped[str] = mapped_column(String(150), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[BeneficiaryStatus] = mapped_column(
        Enum(BeneficiaryStatus, name="beneficiary_status", native_enum=True),
        nullable=False,
        default=BeneficiaryStatus.ACTIVE,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
