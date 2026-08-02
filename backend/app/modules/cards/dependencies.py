import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.accounts.repository import AccountRepository
from app.modules.cards.models import Card
from app.modules.cards.repository import CardRepository
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer


async def get_owned_card(
    card_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> Card:
    card = await CardRepository(session).get_by_id(card_id)
    if card is None:
        raise NotFoundError("Card not found")

    account = await AccountRepository(session).get_by_id(card.account_id)
    if account is None or account.customer_id != customer.id:
        raise NotFoundError("Card not found")

    return card
