import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.modules.accounts.models import AccountStatus
from app.modules.accounts.repository import AccountRepository
from app.modules.exchange_rates.repository import ExchangeRateRepository
from app.modules.transactions.repository import TransferConfirmationRepository


def _extract_otp(calls: list, reference_number: str | None = None) -> str:
    for name, args in calls:
        if name == "send_notification_task" and args[2] == "transfer_otp":
            context = args[3]
            if reference_number is None or context.get("reference_number") == reference_number:
                return context["otp_code"]
    raise AssertionError("No OTP notification was dispatched")


async def _make_active_account(db_session, customer_id, account_number, currency="AZN", balance="1000.00"):
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


async def _register_second_customer(client: AsyncClient, email: str, stub_background_tasks) -> dict:
    from datetime import date

    from tests.conftest import register_and_confirm

    payload = {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Second",
        "last_name": "Customer",
        "date_of_birth": str(date(1994, 4, 4)),
        "phone_number": "+994701234000",
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
    }
    await register_and_confirm(client, stub_background_tasks, payload)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass1"})
    return login.json()


@pytest.mark.asyncio
async def test_transfer_otp_is_delivered_via_email_by_default(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    """
    Regression test for a real bug found during an OTP-delivery audit:
    initiate_transfer used to hardcode the "sms" channel for the transfer
    OTP, which meant a customer with only a real (SMTP-configured) email
    address had no delivery path for it at all — see
    app/core/config.py's otp_delivery_channel docstring. The default is
    now "email"; this locks that in.
    """
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXNOTP01", "AZN", "500.00")

    other_email = f"receiver_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXNOTP02", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXNOTP02",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert initiate.status_code == 201

    otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "transfer_otp"
    ]
    assert len(otp_calls) == 1, f"expected exactly one OTP notification dispatch, got {len(otp_calls)}"
    channel = otp_calls[0][1]
    assert channel == "email", f"transfer OTP was dispatched via {channel!r}, expected 'email'"


@pytest.mark.asyncio
async def test_resend_otp_invalidates_the_previous_code(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXNRSD01", "AZN", "500.00")

    other_email = f"receiver_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXNRSD02", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXNRSD02",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]
    original_otp = _extract_otp(stub_background_tasks)

    resend = await client.post(
        f"/api/v1/transactions/{transaction_id}/resend-otp", headers=registered_customer["headers"]
    )
    assert resend.status_code == 200
    assert resend.json()["otp_expires_in_seconds"] > 0

    new_otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "transfer_otp"
    ]
    assert len(new_otp_calls) == 2, "expected the original send plus one resend"
    new_otp = new_otp_calls[-1][3]["otp_code"]
    assert new_otp != original_otp, "resend must issue a genuinely new code, not repeat the old one"

    old_code_attempt = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": original_otp},
        headers=registered_customer["headers"],
    )
    assert old_code_attempt.status_code in (400, 401, 422), (
        f"expected the invalidated old OTP to be rejected, got {old_code_attempt.status_code}"
    )

    new_code_attempt = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": new_otp},
        headers=registered_customer["headers"],
    )
    assert new_code_attempt.status_code == 200
    assert new_code_attempt.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_resend_otp_resets_the_attempt_counter(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXNRSD03", "AZN", "500.00")

    other_email = f"receiver2_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXNRSD04", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXNRSD04",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    for _ in range(3):
        await client.post(
            f"/api/v1/transactions/{transaction_id}/confirm",
            json={"otp_code": "000000"},
            headers=registered_customer["headers"],
        )

    await client.post(f"/api/v1/transactions/{transaction_id}/resend-otp", headers=registered_customer["headers"])
    otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "transfer_otp"
    ]
    new_otp = otp_calls[-1][3]["otp_code"]

    confirm = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": new_otp},
        headers=registered_customer["headers"],
    )
    assert confirm.status_code == 200, "a fresh OTP after resend should have a full new attempt budget"


@pytest.mark.asyncio
async def test_cannot_resend_otp_for_someone_elses_transaction(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXNRSD05", "AZN", "500.00")

    other_email = f"receiver3_{unique_email}"
    other_tokens = await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXNRSD06", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXNRSD06",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}
    response = await client.post(f"/api/v1/transactions/{transaction_id}/resend-otp", headers=other_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_same_currency_transfer_end_to_end(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXN0001", "AZN", "500.00")

    other_email = f"receiver_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    receiver = await _make_active_account(db_session, receiver_customer.id, "TXN0002", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0002",
            "amount": "150.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert initiate.status_code == 201
    body = initiate.json()
    transaction_id = body["transaction"]["id"]
    assert body["transaction"]["status"] == "PENDING"

    otp_code = _extract_otp(stub_background_tasks)

    confirm = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=registered_customer["headers"],
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "SUCCESS"

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == 350
    assert receiver.balance == 150

    detail = await client.get(
        f"/api/v1/transactions/{transaction_id}", headers=registered_customer["headers"]
    )
    entries = detail.json()["ledger_entries"]
    assert len(entries) == 2
    debit = next(e for e in entries if e["entry_type"] == "DEBIT")
    credit = next(e for e in entries if e["entry_type"] == "CREDIT")
    assert debit["amount"] == "150.00"
    assert credit["amount"] == "150.00"
    assert debit["balance_after"] == "350.00"
    assert credit["balance_after"] == "150.00"


@pytest.mark.asyncio
async def test_cross_currency_transfer_converts_amount(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    rates = ExchangeRateRepository(db_session)
    rates.create(source_currency="USD", target_currency="AZN", rate="1.70000000")
    await db_session.commit()

    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXN0003", "USD", "200.00")

    other_email = f"recv2_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    receiver = await _make_active_account(db_session, receiver_customer.id, "TXN0004", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0004",
            "amount": "100.00",
            "currency": "USD",
        },
        headers=registered_customer["headers"],
    )
    assert initiate.status_code == 201
    transaction_id = initiate.json()["transaction"]["id"]
    assert initiate.json()["transaction"]["converted_amount"] == "170.00"

    otp_code = _extract_otp(stub_background_tasks)
    confirm = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=registered_customer["headers"],
    )
    assert confirm.status_code == 200

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == 100
    assert receiver.balance == 170


@pytest.mark.asyncio
async def test_transfer_without_exchange_rate_fails(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXN0005", "GBP", "100.00")

    other_email = f"recv3_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXN0006", "JPY", "0.00")

    response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0006",
            "amount": "10.00",
            "currency": "GBP",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "EXCHANGE_RATE_NOT_FOUND"


@pytest.mark.asyncio
async def test_insufficient_balance_rejected(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    sender_customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, sender_customer.id, "TXN0007", "AZN", "10.00")

    other_email = f"recv4_{unique_email}"
    await _register_second_customer(client, other_email, stub_background_tasks)
    from sqlalchemy import select

    from app.modules.customers.models import Customer
    from app.modules.users.models import User

    result = await db_session.execute(
        select(Customer).join(User, User.id == Customer.user_id).where(User.email == other_email.lower())
    )
    receiver_customer = result.scalar_one()
    await _make_active_account(db_session, receiver_customer.id, "TXN0008", "AZN", "0.00")

    response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0008",
            "amount": "500.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "INSUFFICIENT_BALANCE"


@pytest.mark.asyncio
async def test_cannot_transfer_from_blocked_account(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0009", "AZN", "100.00")
    sender.status = AccountStatus.BLOCKED
    await db_session.commit()

    await _make_active_account(db_session, customer.id, "TXN0010", "AZN", "0.00")

    response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0010",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ACCOUNT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_cannot_transfer_to_same_account(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    account = await _make_active_account(db_session, customer.id, "TXN0011", "AZN", "100.00")

    response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(account.id),
            "receiver_account_number": "TXN0011",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "SAME_ACCOUNT_TRANSFER"


@pytest.mark.asyncio
async def test_currency_mismatch_rejected(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0012", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0013", "AZN", "0.00")

    response = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0013",
            "amount": "10.00",
            "currency": "USD",
        },
        headers=registered_customer["headers"],
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CURRENCY_MISMATCH"


@pytest.mark.asyncio
async def test_wrong_otp_is_rejected_and_tracks_attempts(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0014", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0015", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0015",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    response = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": "000000"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_OTP"
    assert "4 attempt" in response.json()["message"]


@pytest.mark.asyncio
async def test_exhausting_otp_attempts_fails_the_transaction(
    client: AsyncClient, db_session, registered_customer: dict
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0016", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0017", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0017",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]

    last_response = None
    for _ in range(5):
        last_response = await client.post(
            f"/api/v1/transactions/{transaction_id}/confirm",
            json={"otp_code": "000000"},
            headers=registered_customer["headers"],
        )

    assert last_response.status_code == 403
    assert last_response.json()["error_code"] == "TOO_MANY_OTP_ATTEMPTS"

    # The transaction is now cancelled — even the correct OTP won't work.
    followup = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": "111111"},
        headers=registered_customer["headers"],
    )
    assert followup.status_code == 409
    assert followup.json()["error_code"] == "TRANSACTION_ALREADY_PROCESSED"


@pytest.mark.asyncio
async def test_expired_otp_is_rejected(
    client: AsyncClient, db_session, registered_customer: dict, stub_background_tasks
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0018", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0019", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0019",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]
    otp_code = _extract_otp(stub_background_tasks)

    confirmations = TransferConfirmationRepository(db_session)
    import uuid as uuid_mod

    confirmation = await confirmations.get_by_transaction_id(uuid_mod.UUID(transaction_id))
    confirmation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.add(confirmation)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "OTP_EXPIRED"


@pytest.mark.asyncio
async def test_cannot_confirm_someone_elses_transaction(
    client: AsyncClient, db_session, registered_customer: dict, unique_email: str, stub_background_tasks
):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0020", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0021", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0021",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    transaction_id = initiate.json()["transaction"]["id"]
    otp_code = _extract_otp(stub_background_tasks)

    other_email = f"intruder_{unique_email}"
    other_tokens = await _register_second_customer(client, other_email, stub_background_tasks)
    other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}

    response = await client.post(
        f"/api/v1/transactions/{transaction_id}/confirm",
        json={"otp_code": otp_code},
        headers=other_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_by_reference_number(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0022", "AZN", "100.00")
    await _make_active_account(db_session, customer.id, "TXN0023", "AZN", "0.00")

    initiate = await client.post(
        "/api/v1/transactions/transfer",
        json={
            "sender_account_id": str(sender.id),
            "receiver_account_number": "TXN0023",
            "amount": "10.00",
            "currency": "AZN",
        },
        headers=registered_customer["headers"],
    )
    reference = initiate.json()["transaction"]["reference_number"]

    response = await client.get(
        f"/api/v1/transactions/search?reference={reference}",
        headers=registered_customer["headers"],
    )
    assert response.status_code == 200
    assert response.json()["reference_number"] == reference


@pytest.mark.asyncio
async def test_list_transactions_is_paginated(client: AsyncClient, db_session, registered_customer: dict):
    customer = registered_customer["customer"]
    sender = await _make_active_account(db_session, customer.id, "TXN0024", "AZN", "1000.00")
    await _make_active_account(db_session, customer.id, "TXN0025", "AZN", "0.00")

    for _ in range(3):
        await client.post(
            "/api/v1/transactions/transfer",
            json={
                "sender_account_id": str(sender.id),
                "receiver_account_number": "TXN0025",
                "amount": "5.00",
                "currency": "AZN",
            },
            headers=registered_customer["headers"],
        )

    response = await client.get(
        "/api/v1/transactions?page=1&page_size=2", headers=registered_customer["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
