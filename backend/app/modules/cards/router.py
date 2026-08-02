from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.cards.dependencies import get_owned_card
from app.modules.cards.models import Card
from app.modules.cards.repository import CardRepository
from app.modules.cards.schemas import CardResponse
from app.modules.customers.dependencies import get_current_customer
from app.modules.customers.models import Customer

router = APIRouter(prefix="/api/v1/cards", tags=["cards"])


@router.get("", response_model=list[CardResponse], summary="List the current customer's cards")
async def list_cards(
    customer: Customer = Depends(get_current_customer),
    session: AsyncSession = Depends(get_db),
) -> list[CardResponse]:
    cards = await CardRepository(session).list_for_customer(customer.id)
    return [CardResponse.model_validate(c) for c in cards]


@router.get("/{card_id}", response_model=CardResponse, summary="Get card details (masked number)")
async def get_card(card: Card = Depends(get_owned_card)) -> CardResponse:
    return CardResponse.model_validate(card)
