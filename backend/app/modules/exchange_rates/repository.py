from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.exchange_rates.models import ExchangeRate


class ExchangeRateRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_active_rate(self, source_currency: str, target_currency: str) -> ExchangeRate | None:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.source_currency == source_currency,
                ExchangeRate.target_currency == target_currency,
                ExchangeRate.is_active.is_(True),
                ExchangeRate.valid_from <= now,
            )
            .where((ExchangeRate.valid_to.is_(None)) | (ExchangeRate.valid_to > now))
            .order_by(ExchangeRate.valid_from.desc())
        )
        return result.scalars().first()

    async def list_active(self) -> list[ExchangeRate]:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(ExchangeRate)
            .where(ExchangeRate.is_active.is_(True), ExchangeRate.valid_from <= now)
            .where((ExchangeRate.valid_to.is_(None)) | (ExchangeRate.valid_to > now))
            .order_by(ExchangeRate.source_currency, ExchangeRate.target_currency)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[ExchangeRate]:
        """Admin view — includes inactive/expired rates for full auditability."""
        result = await self._session.execute(
            select(ExchangeRate).order_by(ExchangeRate.created_at.desc())
        )
        return list(result.scalars().all())

    def create(
        self,
        *,
        source_currency: str,
        target_currency: str,
        rate: Decimal,
        is_active: bool = True,
    ) -> ExchangeRate:
        exchange_rate = ExchangeRate(
            source_currency=source_currency,
            target_currency=target_currency,
            rate=rate,
            is_active=is_active,
        )
        self._session.add(exchange_rate)
        return exchange_rate
