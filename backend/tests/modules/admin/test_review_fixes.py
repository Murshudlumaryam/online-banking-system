import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_search_customers_by_name(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    response = await client.get(
        "/api/v1/admin/customers", params={"search": "Test"}, headers=admin_headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["first_name"] == "Test" for item in items), items

    phone_number = registered_customer["customer"].phone_number
    response_by_phone = await client.get(
        "/api/v1/admin/customers", params={"search": phone_number}, headers=admin_headers
    )
    assert any(item["phone_number"] == phone_number for item in response_by_phone.json()["items"])


@pytest.mark.asyncio
async def test_admin_customer_search_with_no_match_returns_empty(client: AsyncClient, admin_headers: dict):
    response = await client.get(
        "/api/v1/admin/customers", params={"search": "definitely-does-not-exist-xyz123"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_admin_can_search_accounts_by_account_number(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    create_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account = create_response.json()
    partial_number = account["account_number"][:10]

    search_response = await client.get(
        "/api/v1/admin/accounts", params={"search": partial_number}, headers=admin_headers
    )
    assert search_response.status_code == 200
    items = search_response.json()["items"]
    assert any(item["id"] == account["id"] for item in items)


@pytest.mark.asyncio
async def test_admin_can_search_transactions_by_reference(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account_id = account_response.json()["id"]
    deposit_response = await client.post(
        f"/api/v1/admin/accounts/{account_id}/deposit",
        json={"amount": "10.00", "currency": "AZN"},
        headers=admin_headers,
    )
    reference = deposit_response.json()["reference_number"]

    search_response = await client.get(
        "/api/v1/admin/transactions", params={"search": reference[:10]}, headers=admin_headers
    )
    assert search_response.status_code == 200
    items = search_response.json()["items"]
    assert any(item["reference_number"] == reference for item in items)


@pytest.mark.asyncio
async def test_admin_can_list_all_cards(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account_id = account_response.json()["id"]
    card_response = await client.post(
        "/api/v1/admin/cards", json={"account_id": account_id, "card_type": "DEBIT"}, headers=admin_headers
    )
    assert card_response.status_code == 201
    card_id = card_response.json()["id"]

    list_response = await client.get("/api/v1/admin/cards", headers=admin_headers)
    assert list_response.status_code == 200
    assert any(item["id"] == card_id for item in list_response.json()["items"])


@pytest.mark.asyncio
async def test_admin_can_list_all_beneficiaries(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    target_account_number = account_response.json()["account_number"]

    create_response = await client.post(
        "/api/v1/beneficiaries",
        json={"beneficiary_account_number": target_account_number, "beneficiary_name": "Test Payee"},
        headers=registered_customer["headers"],
    )
    assert create_response.status_code == 201
    beneficiary_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/admin/beneficiaries", headers=admin_headers)
    assert list_response.status_code == 200
    assert any(item["id"] == beneficiary_id for item in list_response.json()["items"])


@pytest.mark.asyncio
async def test_admin_can_create_a_new_customer(client: AsyncClient, admin_headers: dict):
    unique = uuid.uuid4().hex[:10]
    response = await client.post(
        "/api/v1/admin/customers",
        json={
            "email": f"branch_walkin_{unique}@example.com",
            "temporary_password": "TempPass123",
            "first_name": "Walkin",
            "last_name": "Customer",
            "date_of_birth": "1985-05-05",
            "phone_number": "+994501230000",
            "national_id": f"WALKIN{unique.upper()}",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Walkin"

    # The temporary password should actually work — this is what makes it
    # a real, usable account and not just a database row.
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": f"branch_walkin_{unique}@example.com", "password": "TempPass123"},
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_admin_create_customer_rejects_duplicate_email(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    unique = uuid.uuid4().hex[:10]
    response = await client.post(
        "/api/v1/admin/customers",
        json={
            "email": registered_customer["email"],  # already registered
            "temporary_password": "TempPass123",
            "first_name": "Duplicate",
            "last_name": "Email",
            "date_of_birth": "1985-05-05",
            "phone_number": "+994501230001",
            "national_id": f"DUP{unique.upper()}",
        },
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_customer_cannot_create_customers(client: AsyncClient, registered_customer: dict):
    unique = uuid.uuid4().hex[:10]
    response = await client.post(
        "/api/v1/admin/customers",
        json={
            "email": f"unauthorized_{unique}@example.com",
            "temporary_password": "TempPass123",
            "first_name": "No",
            "last_name": "Permission",
            "date_of_birth": "1985-05-05",
            "phone_number": "+994501230002",
            "national_id": f"NOPERM{unique.upper()}",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_customer_can_block_own_card(client: AsyncClient, admin_headers: dict, registered_customer: dict):
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account_id = account_response.json()["id"]
    card_response = await client.post(
        "/api/v1/admin/cards", json={"account_id": account_id, "card_type": "DEBIT"}, headers=admin_headers
    )
    card_id = card_response.json()["id"]

    block_response = await client.post(
        f"/api/v1/cards/{card_id}/block", headers=registered_customer["headers"]
    )
    assert block_response.status_code == 200
    assert block_response.json()["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_customer_cannot_block_an_already_blocked_card(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account_id = account_response.json()["id"]
    card_response = await client.post(
        "/api/v1/admin/cards", json={"account_id": account_id, "card_type": "DEBIT"}, headers=admin_headers
    )
    card_id = card_response.json()["id"]

    await client.post(f"/api/v1/cards/{card_id}/block", headers=registered_customer["headers"])
    second_attempt = await client.post(f"/api/v1/cards/{card_id}/block", headers=registered_customer["headers"])
    assert second_attempt.status_code == 409


@pytest.mark.asyncio
async def test_customer_cannot_block_someone_elses_card(
    client: AsyncClient, admin_headers: dict, registered_customer: dict, unique_email: str, stub_background_tasks
):
    from tests.conftest import register_and_confirm

    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(registered_customer["customer"].id), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    account_id = account_response.json()["id"]
    card_response = await client.post(
        "/api/v1/admin/cards", json={"account_id": account_id, "card_type": "DEBIT"}, headers=admin_headers
    )
    card_id = card_response.json()["id"]

    unique = uuid.uuid4().hex[:10]
    await register_and_confirm(
        client,
        stub_background_tasks,
        {
            "email": f"other_{unique_email}",
            "password": "StrongPass1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": "1992-02-02",
            "phone_number": "+994501230099",
            "national_id": f"OTH{unique.upper()}",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login", json={"email": f"other_{unique_email}", "password": "StrongPass1"}
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.post(f"/api/v1/cards/{card_id}/block", headers=other_headers)
    assert response.status_code == 404
