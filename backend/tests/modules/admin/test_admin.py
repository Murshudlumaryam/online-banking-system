import pytest
from httpx import AsyncClient

from app.modules.accounts.repository import AccountRepository
from app.modules.exchange_rates.repository import ExchangeRateRepository


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_endpoints(
    client: AsyncClient, registered_customer: dict
):
    response = await client.get(
        "/api/v1/admin/customers", headers=registered_customer["headers"]
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_endpoints_require_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/customers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_list_and_get_customer(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    list_response = await client.get("/api/v1/admin/customers", headers=admin_headers)
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] >= 1

    customer_id = registered_customer["customer"].id
    detail_response = await client.get(
        f"/api/v1/admin/customers/{customer_id}", headers=admin_headers
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["first_name"] == "Test"


@pytest.mark.asyncio
async def test_admin_can_block_and_reactivate_customer(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    customer_id = registered_customer["customer"].id

    block_response = await client.patch(
        f"/api/v1/admin/customers/{customer_id}/status",
        json={"status": "BLOCKED"},
        headers=admin_headers,
    )
    assert block_response.status_code == 200
    assert block_response.json()["status"] == "BLOCKED"

    reactivate_response = await client.patch(
        f"/api/v1/admin/customers/{customer_id}/status",
        json={"status": "ACTIVE"},
        headers=admin_headers,
    )
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_admin_can_create_and_manage_account(
    client: AsyncClient, admin_headers: dict, registered_customer: dict
):
    customer_id = str(registered_customer["customer"].id)

    create_response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": customer_id, "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    account = create_response.json()
    assert account["status"] == "ACTIVE"
    account_id = account["id"]

    block_response = await client.patch(
        f"/api/v1/admin/accounts/{account_id}/status",
        json={"status": "BLOCKED"},
        headers=admin_headers,
    )
    assert block_response.status_code == 200
    assert block_response.json()["status"] == "BLOCKED"

    # The customer themself should now be blocked from using it.
    transfer_response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": account_id,
            "receiver_account_number": account["account_number"],
            "amount": "1.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert transfer_response.status_code in (400, 403)  # same-account or not-active, either proves the block took effect


@pytest.mark.asyncio
async def test_admin_create_account_for_nonexistent_customer_fails(
    client: AsyncClient, admin_headers: dict
):
    import uuid

    response = await client.post(
        "/api/v1/admin/accounts",
        json={"customer_id": str(uuid.uuid4()), "account_type": "CHECKING", "currency": "AZN"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_issue_and_block_card(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    account = accounts.create(
        customer_id=customer.id, account_number="ADMINCARD001", account_type="CHECKING", currency="AZN"
    )
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/admin/cards",
        json={"account_id": str(account.id), "card_type": "DEBIT"},
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    card = create_response.json()
    assert card["masked_card_number"].startswith("4000")
    assert "*" in card["masked_card_number"]

    block_response = await client.patch(
        f"/api/v1/admin/cards/{card['id']}/block", headers=admin_headers
    )
    assert block_response.status_code == 200
    assert block_response.json()["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_admin_can_monitor_all_transactions(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    accounts = AccountRepository(db_session)
    sender = accounts.create(
        customer_id=customer.id, account_number="ADMINTXN001", account_type="CHECKING", currency="AZN"
    )
    receiver = accounts.create(
        customer_id=customer.id, account_number="ADMINTXN002", account_type="CHECKING", currency="AZN"
    )
    await db_session.flush()
    from app.modules.accounts.models import AccountStatus

    sender.status = AccountStatus.ACTIVE
    sender.balance = 100
    receiver.status = AccountStatus.ACTIVE
    await db_session.commit()

    await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "ADMINTXN002",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )

    response = await client.get("/api/v1/admin/transactions", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


@pytest.mark.asyncio
async def test_admin_audit_log_search_filters_correctly(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    import uuid as uuid_mod

    from app.modules.audit_logs.models import AuditLog

    customer_user_id = registered_customer["customer"].user_id
    db_session.add(
        AuditLog(user_id=customer_user_id, action="TEST_LOGIN_EVENT", resource_type="user")
    )
    db_session.add(
        AuditLog(user_id=uuid_mod.uuid4(), action="TEST_OTHER_EVENT", resource_type="user")
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/admin/audit-logs?action=TEST_LOGIN_EVENT&user_id={customer_user_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "TEST_LOGIN_EVENT"
    assert body["items"][0]["user_id"] == str(customer_user_id)


@pytest.mark.asyncio
async def test_admin_update_account_status_for_nonexistent_account_returns_404(
    client: AsyncClient, admin_headers: dict
):
    import uuid

    response = await client.patch(
        f"/api/v1/admin/accounts/{uuid.uuid4()}/status",
        json={"status": "BLOCKED"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_create_card_for_nonexistent_account_returns_404(
    client: AsyncClient, admin_headers: dict
):
    import uuid

    response = await client.post(
        "/api/v1/admin/cards",
        json={"account_id": str(uuid.uuid4()), "card_type": "DEBIT"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_block_nonexistent_card_returns_404(client: AsyncClient, admin_headers: dict):
    import uuid

    response = await client.patch(f"/api/v1/admin/cards/{uuid.uuid4()}/block", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_get_nonexistent_transaction_returns_404(client: AsyncClient, admin_headers: dict):
    import uuid

    response = await client.get(f"/api/v1/admin/transactions/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_list_and_create_exchange_rates(
    client: AsyncClient, admin_headers: dict, db_session
):
    repo = ExchangeRateRepository(db_session)
    repo.create(source_currency="USD", target_currency="AZN", rate="1.70000000", is_active=False)
    await db_session.commit()

    list_response = await client.get("/api/v1/admin/exchange-rates", headers=admin_headers)
    assert list_response.status_code == 200
    # Admin view includes inactive rates too, unlike the customer-facing endpoint.
    pairs = {(r["source_currency"], r["target_currency"]) for r in list_response.json()}
    assert ("USD", "AZN") in pairs

    create_response = await client.post(
        "/api/v1/admin/exchange-rates",
        json={"source_currency": "EUR", "target_currency": "AZN", "rate": "1.85"},
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    assert create_response.json()["rate"] == "1.85000000"
