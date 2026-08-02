import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ExchangeRateResponse(BaseModel):
    id: uuid.UUID
    source_currency: str
    target_currency: str
    rate: Decimal
    valid_from: datetime
    valid_to: datetime | None

    model_config = {"from_attributes": True}
