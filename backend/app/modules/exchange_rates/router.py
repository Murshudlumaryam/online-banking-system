from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.exchange_rates.repository import ExchangeRateRepository
from app.modules.exchange_rates.schemas import ExchangeRateResponse
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/exchange-rates", tags=["exchange-rates"])


@router.get(
    "",
    response_model=list[ExchangeRateResponse],
    summary="List currently active exchange rates",
)
async def list_exchange_rates(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ExchangeRateResponse]:
    rates = await ExchangeRateRepository(session).list_active()
    return [ExchangeRateResponse.model_validate(r) for r in rates]
