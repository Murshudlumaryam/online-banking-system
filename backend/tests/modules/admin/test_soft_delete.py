import uuid
from datetime import date

import pytest
from httpx import AsyncClient


def _customer_payload(email: str) -> dict:
    return {
        "email": email,
        "temporary_password": "StrongPass1",
        "first_name": "Soft",
        "last_name": "Delete",
        "date_of_birth": str(date(1990, 1, 1)),
        "phone_number": "+994500001001",
        "national_id": f"SOFTDEL{uuid.uuid4().hex[:10].upper()}",
    }


@pytest.mark.asyncio
async def test_admin_can_delete_and_restore_a_customer(client: AsyncClient, admin_headers: dict, unique_email: str):
    create_response = await client.post(
        "/api/v1/admin/customers", json=_customer_payload(unique_email), headers=admin_headers
    )
    assert create_response.status_code == 201
    customer_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/admin/customers/{customer_id}", headers=admin_headers)
    assert delete_response.status_code == 204

    # Gone from the normal list and from direct lookup...
    get_response = await client.get(f"/api/v1/admin/customers/{customer_id}", headers=admin_headers)
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/admin/customers", headers=admin_headers)
    assert all(item["id"] != customer_id for item in list_response.json()["items"])

    # ...but visible in the deleted list.
    deleted_response = await client.get("/api/v1/admin/customers/deleted", headers=admin_headers)
    assert deleted_response.status_code == 200
    assert any(item["id"] == customer_id for item in deleted_response.json()["items"])

    # Restoring brings it back to the normal list.
    restore_response = await client.post(f"/api/v1/admin/customers/{customer_id}/restore", headers=admin_headers)
    assert restore_response.status_code == 200
    assert restore_response.json()["id"] == customer_id

    get_after_restore = await client.get(f"/api/v1/admin/customers/{customer_id}", headers=admin_headers)
    assert get_after_restore.status_code == 200

    deleted_after_restore = await client.get("/api/v1/admin/customers/deleted", headers=admin_headers)
    assert all(item["id"] != customer_id for item in deleted_after_restore.json()["items"])


@pytest.mark.asyncio
async def test_deleting_an_already_deleted_customer_is_rejected(
    client: AsyncClient, admin_headers: dict, unique_email: str
):
    create_response = await client.post(
        "/api/v1/admin/customers", json=_customer_payload(unique_email), headers=admin_headers
    )
    customer_id = create_response.json()["id"]
    await client.delete(f"/api/v1/admin/customers/{customer_id}", headers=admin_headers)

    second_delete = await client.delete(f"/api/v1/admin/customers/{customer_id}", headers=admin_headers)
    assert second_delete.status_code == 409


@pytest.mark.asyncio
async def test_restoring_a_non_deleted_customer_is_rejected(
    client: AsyncClient, admin_headers: dict, unique_email: str
):
    create_response = await client.post(
        "/api/v1/admin/customers", json=_customer_payload(unique_email), headers=admin_headers
    )
    customer_id = create_response.json()["id"]

    response = await client.post(f"/api/v1/admin/customers/{customer_id}/restore", headers=admin_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_customer_cannot_delete_or_restore_customers(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    second_email = f"soft_delete_perm_{uuid.uuid4().hex[:10]}@example.com"
    create_response = await client.post(
        "/api/v1/admin/customers", json=_customer_payload(second_email), headers=admin_headers
    )
    assert create_response.status_code == 201
    customer_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/admin/customers/{customer_id}", headers=registered_customer["headers"]
    )
    assert delete_response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_and_restore_a_beneficiary(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    # A second account (owned by the same test customer) to act as the
    # beneficiary's target — created via the admin API to keep this test
    # entirely at the HTTP layer, like its siblings.
    account_response = await client.post(
        "/api/v1/admin/accounts",
        json={
            "customer_id": str(registered_customer["customer"].id),
            "account_type": "CHECKING",
            "currency": "AZN",
        },
        headers=admin_headers,
    )
    account_number = account_response.json()["account_number"]

    create_response = await client.post(
        "/api/v1/beneficiaries",
        json={"beneficiary_account_number": account_number, "beneficiary_name": "Soft Delete Target"},
        headers=registered_customer["headers"],
    )
    assert create_response.status_code == 201
    beneficiary_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/admin/beneficiaries/{beneficiary_id}", headers=admin_headers)
    assert delete_response.status_code == 204

    list_response = await client.get("/api/v1/beneficiaries", headers=registered_customer["headers"])
    assert all(item["id"] != beneficiary_id for item in list_response.json())

    deleted_response = await client.get("/api/v1/admin/beneficiaries/deleted", headers=admin_headers)
    assert deleted_response.status_code == 200
    assert any(item["id"] == beneficiary_id for item in deleted_response.json()["items"])

    restore_response = await client.post(
        f"/api/v1/admin/beneficiaries/{beneficiary_id}/restore", headers=admin_headers
    )
    assert restore_response.status_code == 200

    list_after_restore = await client.get("/api/v1/beneficiaries", headers=registered_customer["headers"])
    assert any(item["id"] == beneficiary_id for item in list_after_restore.json())


@pytest.mark.asyncio
async def test_deleting_a_nonexistent_customer_returns_404(client: AsyncClient, admin_headers: dict):
    response = await client.delete(f"/api/v1/admin/customers/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404
