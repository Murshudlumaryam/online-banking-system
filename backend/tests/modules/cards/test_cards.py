from datetime import date

import pytest
from httpx import AsyncClient

from app.modules.accounts.repository import AccountRepository
from app.modules.cards.repository import CardRepository


@pytest.mark.asyncio
async def test_list_cards_returns_masked_numbers(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    cards = CardRepository(db_session)

    account = accounts.create(
        customer_id=customer.id, account_number="AZ01C0001", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    cards.create(
        account_id=account.id,
        raw_card_number="4111111111111111",
        card_type="DEBIT",
        expiry_date=date(2029, 1, 1),
    )
    await db_session.commit()

    response = await client.get("/api/v1/cards", headers=registered_customer["headers"])

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["masked_card_number"] == "4111 **** **** 1111"
    assert "1111111111111111" not in response.text  # full PAN never leaves the server


@pytest.mark.asyncio
async def test_get_card_details(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    cards = CardRepository(db_session)

    account = accounts.create(
        customer_id=customer.id, account_number="AZ01C0002", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    card = cards.create(
        account_id=account.id,
        raw_card_number="5500000000000004",
        card_type="DEBIT",
        expiry_date=date(2030, 5, 1),
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/cards/{card.id}", headers=registered_customer["headers"])

    assert response.status_code == 200
    assert response.json()["masked_card_number"] == "5500 **** **** 0004"


@pytest.mark.asyncio
async def test_cannot_access_another_customers_card(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str
):
    customer1 = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    cards = CardRepository(db_session)

    account = accounts.create(
        customer_id=customer1.id, account_number="AZ01C0003", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    card = cards.create(
        account_id=account.id,
        raw_card_number="4000000000000002",
        card_type="DEBIT",
        expiry_date=date(2028, 3, 1),
    )
    await db_session.commit()

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

    response = await client.get(f"/api/v1/cards/{card.id}", headers=other_headers)
    assert response.status_code == 404
