import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger_entries.models import LedgerEntry, LedgerEntryType


class LedgerEntryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_for_transaction(self, transaction_id: uuid.UUID) -> list[LedgerEntry]:
        result = await self._session.execute(
            select(LedgerEntry)
            .where(LedgerEntry.transaction_id == transaction_id)
            .order_by(LedgerEntry.created_at)
        )
        return list(result.scalars().all())

    async def list_for_account(
        self, account_id: uuid.UUID, *, start: datetime, end: datetime
    ) -> list[LedgerEntry]:
        result = await self._session.execute(
            select(LedgerEntry)
            .where(
                LedgerEntry.account_id == account_id,
                LedgerEntry.created_at >= start,
                LedgerEntry.created_at <= end,
            )
            .order_by(LedgerEntry.created_at)
        )
        return list(result.scalars().all())

    def create(
        self,
        *,
        transaction_id: uuid.UUID,
        account_id: uuid.UUID,
        entry_type: LedgerEntryType,
        amount: Decimal,
        currency: str,
        balance_before: Decimal,
        balance_after: Decimal,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            transaction_id=transaction_id,
            account_id=account_id,
            entry_type=entry_type,
            amount=amount,
            currency=currency,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        self._session.add(entry)
        return entry
