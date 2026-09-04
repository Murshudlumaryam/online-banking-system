import uuid

import pytest
from httpx import AsyncClient

from app.modules.accounts.repository import AccountRepository


@pytest.mark.asyncio
async def test_create_beneficiary_requires_existing_account(
    client: AsyncClient, registered_customer: dict
):
    response = await client.post(
        "/api/v1/beneficiaries",
        json={"beneficiary_account_number": "NONEXISTENT123", "beneficiary_name": "Ghost"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_list_update_delete_beneficiary(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    accounts.create(
        customer_id=customer.id, account_number="BEN0001", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/beneficiaries",
        json={
            "beneficiary_account_number": "BEN0001",
            "beneficiary_name": "Ali Aliyev",
            "nickname": "Ali",
        },
        headers=registered_customer["headers"],
    )
    assert create_response.status_code == 201
    beneficiary_id = create_response.json()["id"]

    list_response = await client.get(
        "/api/v1/beneficiaries", headers=registered_customer["headers"]
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    update_response = await client.patch(
        f"/api/v1/beneficiaries/{beneficiary_id}",
        json={"nickname": "Ali G"},
        headers=registered_customer["headers"],
    )
    assert update_response.status_code == 200
    assert update_response.json()["nickname"] == "Ali G"

    delete_response = await client.delete(
        f"/api/v1/beneficiaries/{beneficiary_id}", headers=registered_customer["headers"]
    )
    assert delete_response.status_code == 204

    list_after_delete = await client.get(
        "/api/v1/beneficiaries", headers=registered_customer["headers"]
    )
    assert list_after_delete.json() == []


@pytest.mark.asyncio
async def test_cannot_access_another_customers_beneficiary(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    from datetime import date

    from tests.conftest import register_and_confirm

    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    accounts.create(
        customer_id=customer.id, account_number="BEN0002", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/beneficiaries",
        json={"beneficiary_account_number": "BEN0002", "beneficiary_name": "Test"},
        headers=registered_customer["headers"],
    )
    beneficiary_id = create_response.json()["id"]

    other_email = f"other_{unique_email}"
    await register_and_confirm(
        client,
        stub_background_tasks,
        {
            "email": other_email,
            "password": "StrongPass1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": str(date(1991, 2, 2)),
            "phone_number": "+994501112222",
            "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongPass1"}
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.patch(
        f"/api/v1/beneficiaries/{beneficiary_id}",
        json={"nickname": "Hacked"},
        headers=other_headers,
    )
    assert response.status_code == 404
