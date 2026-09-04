import uuid
from datetime import date

import pytest
from httpx import AsyncClient


def _valid_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Aysel",
        "last_name": "Mammadova",
        "date_of_birth": str(date(1995, 5, 20)),
        "phone_number": "+994501234567",
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
        "address": "Baku, Azerbaijan",
    }


def _extract_otp(calls: list, user_id: str) -> str:
    matches = [
        args for name, args in calls
        if name == "send_notification_task" and args[2] == "registration_otp" and args[0] == user_id
    ]
    assert matches, "expected a registration_otp notification to have been dispatched"
    return matches[-1][3]["otp_code"]


@pytest.mark.asyncio
async def test_register_creates_user_and_customer(client: AsyncClient, unique_email: str):
    response = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == unique_email.lower()
    assert body["customer"]["first_name"] == "Aysel"
    assert body["customer"]["customer_number"].startswith("CUS-")


@pytest.mark.asyncio
async def test_register_dispatches_a_verification_email_via_the_configured_channel(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    response = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    assert response.status_code == 201
    body = response.json()
    assert body["otp_expires_in_seconds"] > 0

    otp_calls = [
        args for name, args in stub_background_tasks
        if name == "send_notification_task" and args[2] == "registration_otp"
    ]
    assert len(otp_calls) == 1
    assert otp_calls[0][0] == body["id"]
    assert otp_calls[0][1] == "email"  # OTP_DELIVERY_CHANNEL default — see app/core/config.py


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)

    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error_code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_rejects_future_date_of_birth(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)
    payload["date_of_birth"] = "2999-01-01"

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client: AsyncClient, unique_email: str):
    payload = _valid_payload(unique_email)
    payload["password"] = "weak"

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Registration OTP confirmation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_login_before_confirming_registration(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_wrong_registration_otp_is_rejected_and_login_stays_blocked(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]

    wrong = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": "000000"}
    )
    assert wrong.status_code in (400, 401, 422)

    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert login.status_code == 403
    assert login.json()["error_code"] == "EMAIL_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_correct_registration_otp_verifies_the_account_without_auto_login(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    """Confirming registration must not itself issue a JWT/session — the
    customer still has to log in separately, same principle as transfer
    OTP confirmation never creating a session."""
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]
    otp_code = _extract_otp(stub_background_tasks, user_id)

    confirm = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code}
    )
    assert confirm.status_code == 204
    assert confirm.content == b""  # no tokens, no body at all

    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_registration_otp_cannot_be_reused(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]
    otp_code = _extract_otp(stub_background_tasks, user_id)

    first = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code}
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code}
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "REGISTRATION_ALREADY_CONFIRMED"


@pytest.mark.asyncio
async def test_registration_otp_from_one_user_does_not_verify_another(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register1 = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user1_id = register1.json()["id"]
    otp1 = _extract_otp(stub_background_tasks, user1_id)

    other_email = f"other_{unique_email}"
    register2 = await client.post("/api/v1/auth/register", json=_valid_payload(other_email))
    user2_id = register2.json()["id"]

    # user1's OTP against user2's registration must fail — same isolation
    # guarantee as transfer OTPs, enforced here by the UNIQUE FK on
    # registration_confirmations.user_id (see that model's docstring).
    cross = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user2_id, "otp_code": otp1}
    )
    assert cross.status_code in (400, 401, 422)

    login2 = await client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "StrongPass1"}
    )
    assert login2.status_code == 403


@pytest.mark.asyncio
async def test_registration_otp_max_attempts_locks_out_further_tries(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": "000000"}
        )
    assert response.status_code == 403
    assert response.json()["error_code"] in ("REGISTRATION_OTP_MAX_ATTEMPTS", "REGISTRATION_OTP_INVALID")

    # Even the real code no longer works once attempts are exhausted.
    otp_code = _extract_otp(stub_background_tasks, user_id)
    final = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code}
    )
    assert final.status_code == 403


# ---------------------------------------------------------------------------
# Resend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_registration_otp_invalidates_the_previous_code(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]
    original_otp = _extract_otp(stub_background_tasks, user_id)

    resend = await client.post("/api/v1/auth/register/resend-otp", json={"user_id": user_id})
    assert resend.status_code == 200
    assert resend.json()["otp_expires_in_seconds"] > 0

    new_otp = _extract_otp(stub_background_tasks, user_id)
    assert new_otp != original_otp

    old_attempt = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": original_otp}
    )
    assert old_attempt.status_code in (400, 401, 422)

    new_attempt = await client.post(
        "/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": new_otp}
    )
    assert new_attempt.status_code == 204


@pytest.mark.asyncio
async def test_cannot_resend_otp_for_an_already_confirmed_registration(
    client: AsyncClient, unique_email: str, stub_background_tasks
):
    register = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    user_id = register.json()["id"]
    otp_code = _extract_otp(stub_background_tasks, user_id)
    await client.post("/api/v1/auth/register/confirm", json={"user_id": user_id, "otp_code": otp_code})

    resend = await client.post("/api/v1/auth/register/resend-otp", json={"user_id": user_id})
    assert resend.status_code == 409
    assert resend.json()["error_code"] == "REGISTRATION_ALREADY_CONFIRMED"


# ---------------------------------------------------------------------------
# Security: no leakage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_code_never_appears_in_the_register_response(client: AsyncClient, unique_email: str):
    response = await client.post("/api/v1/auth/register", json=_valid_payload(unique_email))
    assert "otp_code" not in response.text
    assert "otp" not in response.json()


@pytest.mark.asyncio
async def test_admin_created_customers_skip_email_verification(
    client: AsyncClient, admin_headers: dict, unique_email: str
):
    """Mirrors AdminService.create_customer's email_verified=True — an
    admin creating a walk-in customer already verified identity in
    person, so there's no email ownership left to prove."""
    admin_email = f"walkin_{unique_email}"
    response = await client.post(
        "/api/v1/admin/customers",
        json={
            "email": admin_email,
            "temporary_password": "TempStrongPass1",
            "first_name": "Walk",
            "last_name": "In",
            "date_of_birth": "1990-01-01",
            "phone_number": "+994501230000",
            "national_id": f"WALKIN{uuid.uuid4().hex[:10].upper()}",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201

    login = await client.post(
        "/api/v1/auth/login", json={"email": admin_email, "password": "TempStrongPass1"}
    )
    assert login.status_code == 200, "admin-created customers must be able to log in immediately"
