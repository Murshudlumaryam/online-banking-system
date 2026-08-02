import pytest
from httpx import AsyncClient

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository


@pytest.mark.asyncio
async def test_get_my_profile(client: AsyncClient, registered_customer: dict):
    response = await client.get("/api/v1/customers/me", headers=registered_customer["headers"])

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Test"
    assert body["customer_number"].startswith("CUS-")


@pytest.mark.asyncio
async def test_get_my_profile_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/customers/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_my_profile_updates_allowed_fields_only(
    client: AsyncClient, registered_customer: dict
):
    response = await client.patch(
        "/api/v1/customers/me",
        json={"phone_number": "+994559998877", "address": "New address, Baku"},
        headers=registered_customer["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phone_number"] == "+994559998877"
    assert body["address"] == "New address, Baku"
    # Identity fields remain unchanged / not accepted by this endpoint at all.
    assert body["first_name"] == "Test"


@pytest.mark.asyncio
async def test_dashboard_reflects_seeded_accounts(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    repo = AccountRepository(db_session)
    acc1 = repo.create(
        customer_id=customer.id, account_number="AZ01TEST0001", account_type="CHECKING", currency="AZN"
    )
    acc1.status = AccountStatus.ACTIVE
    acc1.balance = 150
    acc2 = repo.create(
        customer_id=customer.id, account_number="AZ01TEST0002", account_type="SAVINGS", currency="USD"
    )
    acc2.status = AccountStatus.ACTIVE
    acc2.balance = 300
    await db_session.commit()
    await db_session.refresh(acc1)
    await db_session.refresh(acc2)

    response = await client.get(
        "/api/v1/customers/me/dashboard", headers=registered_customer["headers"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_accounts"] == 2
    currencies = {b["currency"]: b["total_balance"] for b in body["balances_by_currency"]}
    assert currencies["AZN"] == "150.00"
    assert currencies["USD"] == "300.00"
