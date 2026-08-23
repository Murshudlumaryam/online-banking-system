import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.transactions.models import (
    Transaction,
    TransactionStatus,
    TransactionType,
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

    async def get_for_update(self, transaction_id: uuid.UUID) -> Transaction | None:
        """
        Locks the transaction row itself with SELECT ... FOR UPDATE. This is
        the actual fix for the double-confirmation race condition: without
        it, two concurrent confirm attempts for the *same* transaction each
        independently pass the (unlocked) PENDING check, then both proceed
        to lock and debit the accounts — if the sender's balance happens to
        cover the debit twice, both succeed, producing duplicate ledger
        entries and a double-debited/double-credited balance. Locking the
        transaction row first means the second caller blocks here until the
        first commits, then re-reads a fresh (no longer PENDING) status and
        stops before ever touching the accounts.

        `populate_existing=True` is required, not optional: the caller's
        session already has this row in its identity map from the earlier
        unlocked read in `_get_owned_pending_transaction` (same session,
        same object). Without this flag, SQLAlchemy's default identity-map
        behavior returns that *same* Python object without refreshing its
        attributes — so even though the SQL-level lock correctly serializes
        and waits, `.status` on the returned object can still read the
        stale PENDING value from before the wait, silently defeating the
        whole point of re-checking under lock. Found via a direct
        reproduction test — see
        tests/modules/transactions/test_double_confirmation_vulnerability.py.
        """
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
        self, *, offset: int, limit: int, status: TransactionStatus | None = None, search: str | None = None
    ) -> tuple[list[Transaction], int]:
        query = select(Transaction)
        if status is not None:
            query = query.where(Transaction.status == status)
        if search:
            query = query.where(Transaction.reference_number.ilike(f"%{search}%"))

        count_result = await self._session.execute(query.with_only_columns(Transaction.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    def create(
        self,
        *,
        sender_account_id: uuid.UUID | None,
        receiver_account_id: uuid.UUID | None,
        amount: Decimal,
        currency: str,
        exchange_rate_id: uuid.UUID | None,
        converted_amount: Decimal | None,
        transaction_type: TransactionType = TransactionType.TRANSFER,
        note: str | None = None,
        performed_by_user_id: uuid.UUID | None = None,
    ) -> Transaction:
        transaction = Transaction(
            reference_number=generate_reference_number(),
            transaction_type=transaction_type,
            sender_account_id=sender_account_id,
            receiver_account_id=receiver_account_id,
            amount=amount,
            currency=currency,
            exchange_rate_id=exchange_rate_id,
            converted_amount=converted_amount,
            status=TransactionStatus.PENDING,
            note=note,
            performed_by_user_id=performed_by_user_id,
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

    async def save(self, transaction: Transaction) -> None:
        self._session.add(transaction)
        await self._session.flush()

    async def get_by_reversal_of(self, transaction_id: uuid.UUID) -> Transaction | None:
        """Returns the transaction (if any) whose `reversal_of_transaction_id`
        points at `transaction_id` — i.e. whether this transaction has
        already been reversed once. The UNIQUE constraint on that column
        (migration 0009) is the actual guarantee; this is just how the
        service layer checks it up front for a clean error message."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.reversal_of_transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()


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
