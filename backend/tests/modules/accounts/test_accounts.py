import pytest
from httpx import AsyncClient

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository


@pytest.mark.asyncio
async def test_list_accounts_returns_only_own_accounts(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    repo = AccountRepository(db_session)
    repo.create(customer_id=customer.id, account_number="AZ01A0001", account_type="CHECKING", currency="AZN")
    await db_session.commit()

    response = await client.get("/api/v1/accounts", headers=registered_customer["headers"])

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["account_number"] == "AZ01A0001"


@pytest.mark.asyncio
async def test_get_account_details(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    repo = AccountRepository(db_session)
    account = repo.create(
        customer_id=customer.id, account_number="AZ01A0002", account_type="CHECKING", currency="EUR"
    )
    account.status = AccountStatus.ACTIVE
    account.balance = 42
    await db_session.commit()
    await db_session.refresh(account)

    response = await client.get(
        f"/api/v1/accounts/{account.id}", headers=registered_customer["headers"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "EUR"
    assert body["balance"] == "42.00"


@pytest.mark.asyncio
async def test_get_account_balance(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    repo = AccountRepository(db_session)
    account = repo.create(
        customer_id=customer.id, account_number="AZ01A0003", account_type="CHECKING", currency="AZN"
    )
    account.balance = 99
    await db_session.commit()
    await db_session.refresh(account)

    response = await client.get(
        f"/api/v1/accounts/{account.id}/balance", headers=registered_customer["headers"]
    )

    assert response.status_code == 200
    assert response.json()["balance"] == "99.00"


@pytest.mark.asyncio
async def test_cannot_access_another_customers_account(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str
):
    # Seed an account for customer #1.
    customer1 = registered_customer["customer"]
    repo = AccountRepository(db_session)
    account = repo.create(
        customer_id=customer1.id, account_number="AZ01A0004", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    # Register a second, unrelated customer.
    from datetime import date

    other_email = f"other_{unique_email}"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "password": "StrongPass1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": str(date(1991, 2, 2)),
            "phone_number": "+994501112222",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongPass1"}
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.get(f"/api/v1/accounts/{account.id}", headers=other_headers)

    # 404, not 403 — never confirm that the resource exists for someone else.
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_account_returns_404(client: AsyncClient, registered_customer: dict):
    import uuid

    response = await client.get(
        f"/api/v1/accounts/{uuid.uuid4()}", headers=registered_customer["headers"]
    )
    assert response.status_code == 404
