import uuid
from datetime import date

from pydantic import BaseModel

from app.modules.cards.models import CardStatus


class CardResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    masked_card_number: str
    card_type: str
    expiry_date: date
    status: CardStatus

    model_config = {"from_attributes": True}
