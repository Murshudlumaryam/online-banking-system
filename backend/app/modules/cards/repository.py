import secrets
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import Account
from app.modules.cards.models import Card, CardStatus


def _luhn_check_digit(partial_number: str) -> str:
    digits = [int(d) for d in partial_number]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def generate_synthetic_pan(*, bin_prefix: str = "400000") -> str:
    """
    Generates a Luhn-valid, non-real 16-digit PAN for internal debit-card
    issuance. This is a closed-loop bank simulation — there is no real card
    network integration, so the number only needs to be structurally valid
    (useful for demos, receipts, and Luhn-based client-side validation), never
    a real payment card number.
    """
    body = bin_prefix + "".join(str(secrets.randbelow(10)) for _ in range(15 - len(bin_prefix)))
    return body + _luhn_check_digit(body)


class CardRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, card_id: uuid.UUID) -> Card | None:
        result = await self._session.execute(select(Card).where(Card.id == card_id))
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[Card]:
        result = await self._session.execute(
            select(Card)
            .join(Account, Account.id == Card.account_id)
            .where(Account.customer_id == customer_id)
            .order_by(Card.created_at)
        )
        return list(result.scalars().all())

    async def list_all(
        self, *, offset: int, limit: int, status=None
    ) -> tuple[list[Card], int]:
        """Admin-facing: every card in the system, not scoped to one
        customer. See app/modules/admin/router.py's GET /admin/cards."""
        query = select(Card)
        if status is not None:
            query = query.where(Card.status == status)

        count_result = await self._session.execute(query.with_only_columns(Card.id))
        total = len(count_result.all())

        result = await self._session.execute(
            query.order_by(Card.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    def create(
        self,
        *,
        account_id: uuid.UUID,
        raw_card_number: str,
        card_type: str,
        expiry_date: date,
    ) -> Card:
        card = Card(
            account_id=account_id,
            masked_card_number=Card.mask(raw_card_number),
            card_type=card_type,
            expiry_date=expiry_date,
            status=CardStatus.ACTIVE,
        )
        self._session.add(card)
        return card

    async def save(self, card: Card) -> None:
        self._session.add(card)
        await self._session.flush()
