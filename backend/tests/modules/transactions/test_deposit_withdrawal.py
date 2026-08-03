import pytest
from httpx import AsyncClient


async def _create_account(client: AsyncClient, admin_headers: dict, customer_id: str, currency: str = "AZN") -> dict:
    response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": customer_id, "account_type": "CHECKING", "currency": currency},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_admin_can_deposit_into_customer_account(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "250.00", "currency": "AZN", "note": "Cash deposit at branch"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["transaction_type"] == "DEPOSIT"
    assert body["status"] == "SUCCESS"
    assert body["sender_account_id"] is None
    assert body["receiver_account_id"] == account["id"]
    assert body["amount"] == "250.00"
    assert body["note"] == "Cash deposit at branch"

    balance_response = await client.get(
        f"/api/v1/accounts/{account['id']}/balance", headers=registered_customer["headers"]
    )
    assert balance_response.json()["balance"] == "250.00"


@pytest.mark.asyncio
async def test_deposit_writes_a_single_credit_ledger_entry(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "100.00", "currency": "AZN"},
        headers=admin_headers,
    )
    transaction_id = response.json()["id"]

    detail_response = await client.get(
        f"/api/v1/transactions/{transaction_id}", headers=registered_customer["headers"]
    )
    assert detail_response.status_code == 200
    entries = detail_response.json()["ledger_entries"]
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "CREDIT"
    assert entries[0]["balance_before"] == "0.00"
    assert entries[0]["balance_after"] == "100.00"


@pytest.mark.asyncio
async def test_admin_can_withdraw_from_customer_account(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))
    await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "500.00", "currency": "AZN"},
        headers=admin_headers,
    )

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/withdraw",
        json={"amount": "150.00", "currency": "AZN", "note": "ATM withdrawal"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["transaction_type"] == "WITHDRAWAL"
    assert body["sender_account_id"] == account["id"]
    assert body["receiver_account_id"] is None

    balance_response = await client.get(
        f"/api/v1/accounts/{account['id']}/balance", headers=registered_customer["headers"]
    )
    assert balance_response.json()["balance"] == "350.00"


@pytest.mark.asyncio
async def test_withdrawal_with_insufficient_balance_is_rejected(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))
    await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "50.00", "currency": "AZN"},
        headers=admin_headers,
    )

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/withdraw",
        json={"amount": "999.00", "currency": "AZN"},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "INSUFFICIENT_BALANCE"

    # The balance must be untouched — no partial withdrawal.
    balance_response = await client.get(
        f"/api/v1/accounts/{account['id']}/balance", headers=registered_customer["headers"]
    )
    assert balance_response.json()["balance"] == "50.00"


@pytest.mark.asyncio
async def test_deposit_with_wrong_currency_is_rejected(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id), currency="AZN")

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "100.00", "currency": "USD"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CURRENCY_MISMATCH"


@pytest.mark.asyncio
async def test_deposit_into_blocked_account_is_rejected(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))
    await client.patch(
        f"/api/v1/admin/accounts/{account['id']}/status",
        json={"status": "BLOCKED"},
        headers=admin_headers,
    )

    response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "100.00", "currency": "AZN"},
        headers=admin_headers,
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ACCOUNT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_deposit_into_nonexistent_account_returns_404(client: AsyncClient, admin_headers: dict):
    import uuid

    response = await client.post(
        f"/api/v1/admin/accounts/{uuid.uuid4()}/deposit",
        json={"amount": "100.00", "currency": "AZN"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_deposit_or_withdraw(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))

    deposit_response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/deposit",
        json={"amount": "100.00", "currency": "AZN"},
        headers=registered_customer["headers"],
    )
    assert deposit_response.status_code == 403

    withdraw_response = await client.post(
        f"/api/v1/admin/accounts/{account['id']}/withdraw",
        json={"amount": "10.00", "currency": "AZN"},
        headers=registered_customer["headers"],
    )
    assert withdraw_response.status_code == 403


@pytest.mark.asyncio
async def test_negative_and_zero_deposit_amounts_are_rejected(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    account = await _create_account(client, admin_headers, str(registered_customer["customer"].id))

    for amount in ("0", "-50.00"):
        response = await client.post(
            f"/api/v1/admin/accounts/{account['id']}/deposit",
            json={"amount": amount, "currency": "AZN"},
            headers=admin_headers,
        )
        assert response.status_code == 422
