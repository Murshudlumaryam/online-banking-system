import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transactions.models import (
    Transaction,
    TransactionStatus,
    TransferConfirmation,
)


def generate_reference_number() -> str:
    return f"TXN-{secrets.token_hex(8).upper()}"


class TransactionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, transaction_id: uuid.UUID) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def get_by_reference_number(self, reference_number: str) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.reference_number == reference_number)
        )
        return result.scalar_one_or_none()

    async def list_for_customer_accounts(
        self, account_ids: list[uuid.UUID], *, offset: int, limit: int
    ) -> tuple[list[Transaction], int]:
        base_query = select(Transaction).where(
            or_(
                Transaction.sender_account_id.in_(account_ids),
                Transaction.receiver_account_id.in_(account_ids),
            )
        )

        count_result = await self._session.execute(
            select(Transaction.id).where(
                or_(
                    Transaction.sender_account_id.in_(account_ids),
                    Transaction.receiver_account_id.in_(account_ids),
                )
            )
        )
        total = len(count_result.all())

        result = await self._session.execute(
            base_query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_all(
        self, *, offset: int, limit: int, status: TransactionStatus | None = None
    ) -> tuple[list[Transaction], int]:
        query = select(Transaction)
        if status is not None:
            query = query.where(Transaction.status == status)

        count_result = await self._session.execute(query.with_only_columns(Transaction.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    def create(
        self,
        *,
        sender_account_id: uuid.UUID,
        receiver_account_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        exchange_rate_id: uuid.UUID | None,
        converted_amount: Decimal | None,
    ) -> Transaction:
        transaction = Transaction(
            reference_number=generate_reference_number(),
            sender_account_id=sender_account_id,
            receiver_account_id=receiver_account_id,
            amount=amount,
            currency=currency,
            exchange_rate_id=exchange_rate_id,
            converted_amount=converted_amount,
            status=TransactionStatus.PENDING,
        )
        self._session.add(transaction)
        return transaction

    async def mark_failed(self, transaction: Transaction, reason: str) -> None:
        transaction.status = TransactionStatus.FAILED
        transaction.failure_reason = reason
        transaction.completed_at = datetime.now(timezone.utc)
        self._session.add(transaction)

    async def mark_success(self, transaction: Transaction) -> None:
        transaction.status = TransactionStatus.SUCCESS
        transaction.completed_at = datetime.now(timezone.utc)
        self._session.add(transaction)


class TransferConfirmationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_transaction_id(self, transaction_id: uuid.UUID) -> TransferConfirmation | None:
        result = await self._session.execute(
            select(TransferConfirmation).where(TransferConfirmation.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()

    def create(
        self, *, transaction_id: uuid.UUID, otp_code_hash: str, expires_at: datetime
    ) -> TransferConfirmation:
        confirmation = TransferConfirmation(
            transaction_id=transaction_id, otp_code_hash=otp_code_hash, expires_at=expires_at
        )
        self._session.add(confirmation)
        return confirmation

    async def register_failed_attempt(self, confirmation: TransferConfirmation) -> None:
        confirmation.attempts += 1
        self._session.add(confirmation)

    async def mark_verified(self, confirmation: TransferConfirmation) -> None:
        confirmation.verified_at = datetime.now(timezone.utc)
        self._session.add(confirmation)

    @staticmethod
    def is_expired(confirmation: TransferConfirmation) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= now

    @staticmethod
    def attempts_exhausted(confirmation: TransferConfirmation) -> bool:
        return confirmation.attempts >= confirmation.max_attempts
