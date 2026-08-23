import uuid

import pytest
from httpx import AsyncClient

from app.modules.accounts.repository import AccountRepository


async def _issue_card(client: AsyncClient, admin_headers: dict, db_session, customer, account_number: str) -> dict:
    accounts = AccountRepository(db_session)
    account = accounts.create(
        customer_id=customer.id, account_number=account_number, account_type="CHECKING", currency="AZN"
    )
    account.status = "ACTIVE"
    account.balance = 500
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/admin/cards",
        json={"account_id": str(account.id), "card_type": "DEBIT"},
        headers=admin_headers,
    )
    assert create_response.status_code == 201, create_response.text
    return {"card": create_response.json(), "account_id": str(account.id)}


@pytest.mark.asyncio
async def test_admin_can_delete_a_card(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "DELCARD001"
    )
    card_id = issued["card"]["id"]

    delete_response = await client.delete(f"/api/v1/admin/cards/{card_id}", headers=admin_headers)
    assert delete_response.status_code == 204

    # Soft-deleted: gone from the customer's own list...
    list_response = await client.get("/api/v1/cards", headers=registered_customer["headers"])
    assert all(c["id"] != card_id for c in list_response.json())

    # ...and gone from the admin's system-wide list too.
    admin_list_response = await client.get("/api/v1/admin/cards", headers=admin_headers)
    assert all(c["id"] != card_id for c in admin_list_response.json()["items"])

    # ...but a direct fetch by the (former) owner now 404s rather than
    # silently returning a "deleted" card.
    get_response = await client.get(f"/api/v1/cards/{card_id}", headers=registered_customer["headers"])
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_nonexistent_card_returns_404(client: AsyncClient, admin_headers: dict):
    response = await client.delete(f"/api/v1/admin/cards/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_delete_cards(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "DELCARD002"
    )
    response = await client.delete(
        f"/api/v1/cards/{issued['card']['id']}", headers=registered_customer["headers"]
    )
    # No customer-facing DELETE route exists at all for cards.
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_customer_can_pay_with_their_own_card(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "PAYCARD001"
    )
    card_id = issued["card"]["id"]

    response = await client.post(
        f"/api/v1/cards/{card_id}/pay",
        json={"amount": "45.50", "currency": "AZN", "merchant_name": "Corner Grocery"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["transaction_type"] == "CARD_PAYMENT"
    assert body["status"] == "SUCCESS"
    assert body["sender_account_id"] == issued["account_id"]
    assert body["receiver_account_id"] is None
    assert body["card_id"] == card_id
    assert body["note"] == "Corner Grocery"

    balance_response = await client.get(
        f"/api/v1/accounts/{issued['account_id']}/balance", headers=registered_customer["headers"]
    )
    assert balance_response.json()["balance"] == "454.50"


@pytest.mark.asyncio
async def test_card_payment_writes_a_single_debit_ledger_entry(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "PAYCARD002"
    )
    response = await client.post(
        f"/api/v1/cards/{issued['card']['id']}/pay",
        json={"amount": "10.00", "currency": "AZN", "merchant_name": "Coffee Shop"},
        headers=registered_customer["headers"],
    )
    transaction_id = response.json()["id"]

    detail_response = await client.get(
        f"/api/v1/transactions/{transaction_id}", headers=registered_customer["headers"]
    )
    entries = detail_response.json()["ledger_entries"]
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "DEBIT"
    assert entries[0]["balance_before"] == "500.00"
    assert entries[0]["balance_after"] == "490.00"


@pytest.mark.asyncio
async def test_card_payment_with_insufficient_balance_is_rejected(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "PAYCARD003"
    )
    response = await client.post(
        f"/api/v1/cards/{issued['card']['id']}/pay",
        json={"amount": "9999.00", "currency": "AZN", "merchant_name": "Big Purchase"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "INSUFFICIENT_BALANCE"

    balance_response = await client.get(
        f"/api/v1/accounts/{issued['account_id']}/balance", headers=registered_customer["headers"]
    )
    assert balance_response.json()["balance"] == "500.00"


@pytest.mark.asyncio
async def test_blocked_card_cannot_be_used_for_payment(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    issued = await _issue_card(
        client, admin_headers, db_session, registered_customer["customer"], "PAYCARD004"
    )
    await client.patch(f"/api/v1/admin/cards/{issued['card']['id']}/block", headers=admin_headers)

    response = await client.post(
        f"/api/v1/cards/{issued['card']['id']}/pay",
        json={"amount": "5.00", "currency": "AZN", "merchant_name": "Should Fail"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 409
    assert "blocked" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_customer_cannot_pay_with_someone_elses_card(
    client: AsyncClient, admin_headers: dict, db_session, registered_customer: dict
):
    from datetime import date

    from app.modules.customers.repository import CustomerRepository
    from app.modules.users.repository import UserRepository

    users = UserRepository(db_session)
    customers = CustomerRepository(db_session)
    other_user = users.create(email=f"other_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    await db_session.flush()
    other_customer = customers.create(
        user_id=other_user.id, first_name="Other", last_name="Owner",
        date_of_birth=date(1991, 2, 2), phone_number="+994500000901",
        national_id=f"OTH{uuid.uuid4().hex[:12].upper()}",
    )
    await db_session.commit()

    issued = await _issue_card(client, admin_headers, db_session, other_customer, "PAYCARD005")

    response = await client.post(
        f"/api/v1/cards/{issued['card']['id']}/pay",
        json={"amount": "5.00", "currency": "AZN", "merchant_name": "Not Yours"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 404
