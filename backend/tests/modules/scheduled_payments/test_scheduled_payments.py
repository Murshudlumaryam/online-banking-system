import uuid

import pytest
from httpx import AsyncClient

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository


async def _make_active_account(db_session, customer_id, account_number, currency="AZN", balance="500.00"):
    repo = AccountRepository(db_session)
    account = repo.create(
        customer_id=customer_id, account_number=account_number, account_type="CHECKING", currency=currency
    )
    await db_session.flush()
    account.status = AccountStatus.ACTIVE
    account.balance = balance
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_create_list_and_cancel_scheduled_payment(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "SCHED0001")
    await _make_active_account(db_session, customer.id, "SCHED0002", balance="0.00")

    create_response = await client.post(
        "/api/v1/scheduled-payments",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "SCHED0002",
            "amount": "25.00",
            "currency": "AZN",
            "frequency": "MONTHLY",
        },
        headers=registered_customer["headers"],
    )
    assert create_response.status_code == 201
    schedule = create_response.json()
    assert schedule["is_active"] is True
    assert schedule["frequency"] == "MONTHLY"

    list_response = await client.get(
        "/api/v1/scheduled-payments", headers=registered_customer["headers"]
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    cancel_response = await client.delete(
        f"/api/v1/scheduled-payments/{schedule['id']}", headers=registered_customer["headers"]
    )
    assert cancel_response.status_code == 204

    list_after_cancel = await client.get(
        "/api/v1/scheduled-payments", headers=registered_customer["headers"]
    )
    assert list_after_cancel.json()[0]["is_active"] is False


@pytest.mark.asyncio
async def test_create_scheduled_payment_for_nonexistent_account_fails(
    client: AsyncClient, registered_customer: dict
):
    import uuid

    response = await client.post(
        "/api/v1/scheduled-payments",
        json={
            "sender_account_id": str(uuid.uuid4()),
            "receiver_account_number": "SCHED9999",
            "amount": "10.00",
            "currency": "AZN",
            "frequency": "DAILY",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_scheduled_payment_currency_mismatch_fails(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "SCHED0003", currency="AZN")

    response = await client.post(
        "/api/v1/scheduled-payments",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "SCHED0004",
            "amount": "10.00",
            "currency": "USD",
            "frequency": "WEEKLY",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CURRENCY_MISMATCH"


@pytest.mark.asyncio
async def test_cannot_cancel_another_customers_scheduled_payment(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str
):
    from datetime import date

    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "SCHED0005")
    await _make_active_account(db_session, customer.id, "SCHED0006", balance="0.00")

    create_response = await client.post(
        "/api/v1/scheduled-payments",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "SCHED0006",
            "amount": "10.00",
            "currency": "AZN",
            "frequency": "DAILY",
        },
        headers=registered_customer["headers"],
    )
    schedule_id = create_response.json()["id"]

    other_email = f"sched_intruder_{unique_email}"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "password": "StrongPass1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": str(date(1990, 1, 1)),
            "phone_number": "+994501112233",
            "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongPass1"}
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.delete(f"/api/v1/scheduled-payments/{schedule_id}", headers=other_headers)
    assert response.status_code == 404
