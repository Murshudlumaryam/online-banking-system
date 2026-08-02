import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.ledger_entries.models import LedgerEntryType


class LedgerEntryResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    entry_type: LedgerEntryType
    amount: Decimal
    currency: str
    balance_before: Decimal
    balance_after: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}
