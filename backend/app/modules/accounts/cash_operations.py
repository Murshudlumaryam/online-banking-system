import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class CashOperationType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class AccountCashOperation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "account_cash_operations"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_account_cash_operations_amount_positive"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    operation_type: Mapped[CashOperationType] = mapped_column(
        Enum(CashOperationType, name="cash_operation_type", native_enum=True), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    performed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AccountCashOperationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    def create(
        self,
        *,
        account_id: uuid.UUID,
        operation_type: CashOperationType,
        amount: Decimal,
        currency: str,
        balance_before: Decimal,
        balance_after: Decimal,
        performed_by_user_id: uuid.UUID,
        note: str | None,
    ) -> AccountCashOperation:
        operation = AccountCashOperation(
            account_id=account_id,
            operation_type=operation_type,
            amount=amount,
            currency=currency,
            balance_before=balance_before,
            balance_after=balance_after,
            performed_by_user_id=performed_by_user_id,
            note=note,
        )
        self._session.add(operation)
        return operation

    async def list_for_account(
        self, account_id: uuid.UUID, *, start: datetime, end: datetime
    ) -> list[AccountCashOperation]:
        result = await self._session.execute(
            select(AccountCashOperation)
            .where(
                AccountCashOperation.account_id == account_id,
                AccountCashOperation.created_at >= start,
                AccountCashOperation.created_at <= end,
            )
            .order_by(AccountCashOperation.created_at)
        )
        return list(result.scalars().all())
