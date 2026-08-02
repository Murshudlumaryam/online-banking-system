import pytest
from httpx import AsyncClient

from app.modules.exchange_rates.repository import ExchangeRateRepository


@pytest.mark.asyncio
async def test_list_active_exchange_rates(client: AsyncClient, db_session, registered_customer: dict):
    repo = ExchangeRateRepository(db_session)
    repo.create(source_currency="USD", target_currency="AZN", rate="1.70000000")
    repo.create(source_currency="EUR", target_currency="AZN", rate="1.85000000")
    await db_session.commit()

    response = await client.get(
        "/api/v1/exchange-rates", headers=registered_customer["headers"]
    )

    assert response.status_code == 200
    body = response.json()
    pairs = {(r["source_currency"], r["target_currency"]) for r in body}
    assert ("USD", "AZN") in pairs
    assert ("EUR", "AZN") in pairs


@pytest.mark.asyncio
async def test_exchange_rates_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/exchange-rates")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_rate_not_listed(client: AsyncClient, db_session, registered_customer: dict):
    repo = ExchangeRateRepository(db_session)
    repo.create(source_currency="GBP", target_currency="AZN", rate="2.10000000", is_active=False)
    await db_session.commit()

    response = await client.get(
        "/api/v1/exchange-rates", headers=registered_customer["headers"]
    )

    pairs = {(r["source_currency"], r["target_currency"]) for r in response.json()}
    assert ("GBP", "AZN") not in pairs
