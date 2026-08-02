from datetime import date, timedelta

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
async def test_statement_returns_valid_pdf_with_no_transactions(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    account = await _make_active_account(db_session, customer.id, "STMT0001")

    response = await client.get(
        f"/api/v1/accounts/{account.id}/statement", headers=registered_customer["headers"]
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_statement_includes_ledger_entries_after_a_transfer(
    client: AsyncClient, db_session, registered_customer: dict, stub_background_tasks
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "STMT0002", "AZN", "500.00")
    await _make_active_account(db_session, customer.id, "STMT0003", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "STMT0003",
            "amount": "50.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    otp_code = None
    for name, args in stub_background_tasks:
        if name == "send_notification_task" and args[2] == "transfer_otp":
            otp_code = args[3]["otp_code"]
    assert otp_code is not None

    await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=registered_customer["headers"],
    )

    response = await client.get(
        f"/api/v1/accounts/{sender.id}/statement", headers=registered_customer["headers"]
    )
    assert response.status_code == 200
    # A real check that the PDF isn't just the "no transactions" boilerplate:
    # a statement with entries is meaningfully larger than an empty one.
    assert len(response.content) > 2000


@pytest.mark.asyncio
async def test_statement_respects_date_range_query_params(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    account = await _make_active_account(db_session, customer.id, "STMT0004")

    start = (date.today() - timedelta(days=90)).isoformat()
    end = (date.today() - timedelta(days=60)).isoformat()

    response = await client.get(
        f"/api/v1/accounts/{account.id}/statement?start_date={start}&end_date={end}",
        headers=registered_customer["headers"],
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_cannot_get_statement_for_another_customers_account(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str
):
    from datetime import date as date_cls

    customer = registered_customer["customer"]
    account = await _make_active_account(db_session, customer.id, "STMT0005")

    other_email = f"stmt_intruder_{unique_email}"
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "password": "StrongPass1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": str(date_cls(1990, 1, 1)),
            "phone_number": "+994501112233",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongPass1"}
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.get(f"/api/v1/accounts/{account.id}/statement", headers=other_headers)
    assert response.status_code == 404
