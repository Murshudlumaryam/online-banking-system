import uuid
from datetime import date

import pyotp
import pytest
from httpx import AsyncClient


def _register_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "TwoFactor",
        "last_name": "Tester",
        "date_of_birth": str(date(1993, 6, 15)),
        "phone_number": "+994551239876",
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
    }


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/api/v1/auth/register", json=_register_payload(email))
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass1"})
    return response.json()


@pytest.mark.asyncio
async def test_login_without_2fa_returns_tokens_directly(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    assert tokens["mfa_required"] is False
    assert tokens["access_token"]
    assert "refresh_token" not in tokens


@pytest.mark.asyncio
async def test_full_2fa_enrollment_and_login_flow(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup_response = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert setup_response.status_code == 200
    body = setup_response.json()
    secret = body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")

    valid_code = pyotp.TOTP(secret).now()
    enable_response = await client.post(
        "/api/v1/auth/2fa/enable", json={"code": valid_code}, headers=headers
    )
    assert enable_response.status_code == 204

    # Password login must now return an MFA challenge instead of real tokens.
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["mfa_required"] is True
    assert login_body["access_token"] is None
    challenge_token = login_body["challenge_token"]
    assert challenge_token

    verify_code = pyotp.TOTP(secret).now()
    verify_response = await client.post(
        "/api/v1/auth/2fa/verify-login",
        json={"challenge_token": challenge_token, "code": verify_code},
    )
    assert verify_response.status_code == 200
    final_tokens = verify_response.json()
    assert final_tokens["access_token"]
    assert "refresh_token" not in final_tokens
    assert verify_response.cookies.get("refresh_token")


@pytest.mark.asyncio
async def test_enable_2fa_rejects_wrong_code(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/auth/2fa/setup", headers=headers)
    response = await client.post("/api/v1/auth/2fa/enable", json={"code": "000000"}, headers=headers)
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOTP_CODE"


@pytest.mark.asyncio
async def test_enable_2fa_without_setup_first_fails(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = await client.post("/api/v1/auth/2fa/enable", json={"code": "123456"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error_code"] == "TWO_FACTOR_SETUP_NOT_STARTED"


@pytest.mark.asyncio
async def test_verify_mfa_login_rejects_wrong_code(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    await client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    challenge_token = login_response.json()["challenge_token"]

    response = await client.post(
        "/api/v1/auth/2fa/verify-login",
        json={"challenge_token": challenge_token, "code": "000000"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOTP_CODE"


@pytest.mark.asyncio
async def test_verify_mfa_login_rejects_expired_or_invalid_challenge_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/2fa/verify-login",
        json={"challenge_token": "not-a-real-token", "code": "123456"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_MFA_CHALLENGE"


@pytest.mark.asyncio
async def test_disable_2fa_requires_correct_password_and_code(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    await client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    wrong_password_response = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"password": "WrongPass1", "code": pyotp.TOTP(secret).now()},
        headers=headers,
    )
    assert wrong_password_response.status_code == 401

    disable_response = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"password": "StrongPass1", "code": pyotp.TOTP(secret).now()},
        headers=headers,
    )
    assert disable_response.status_code == 204

    # Login should go back to returning tokens directly, no MFA challenge.
    login_response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert login_response.json()["mfa_required"] is False


@pytest.mark.asyncio
async def test_cannot_enable_2fa_twice(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    await client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    second_setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    assert second_setup.status_code == 409
    assert second_setup.json()["error_code"] == "TWO_FACTOR_ALREADY_ENABLED"


@pytest.mark.asyncio
async def test_cannot_disable_2fa_when_not_enabled(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"password": "StrongPass1", "code": "123456"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "TWO_FACTOR_NOT_ENABLED"


@pytest.mark.asyncio
async def test_totp_secret_is_encrypted_at_rest_in_the_database(
    client: AsyncClient, db_session, unique_email: str
):
    """
    Regression test for the Phase 9 hardening item: the raw TOTP secret
    (the value shown to the user + encoded in the QR provisioning URI) must
    never appear verbatim in the `users.totp_secret` column — only its
    Fernet-encrypted ciphertext should be stored.
    """
    from sqlalchemy import select

    from app.core.crypto import decrypt_secret
    from app.modules.users.models import User

    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup_response = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    raw_secret = setup_response.json()["secret"]

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()

    assert user.totp_secret is not None
    assert user.totp_secret != raw_secret, "TOTP secret was stored in plaintext"
    assert decrypt_secret(user.totp_secret) == raw_secret


@pytest.mark.asyncio
async def test_totp_secret_column_is_cleared_not_just_disabled_flag(
    client: AsyncClient, db_session, unique_email: str
):
    """When 2FA is disabled, the encrypted secret itself must be wiped, not
    just the totp_enabled flag flipped — leaving it around after disable
    would mean re-enabling silently reuses an old (and already once shown
    to the user) secret."""
    from sqlalchemy import select

    from app.modules.users.models import User

    tokens = await _register_and_login(client, unique_email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    setup = await client.post("/api/v1/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    await client.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()
    assert user.totp_secret is not None

    await client.post(
        "/api/v1/auth/2fa/disable",
        json={"password": "StrongPass1", "code": pyotp.TOTP(secret).now()},
        headers=headers,
    )

    await db_session.refresh(user)
    assert user.totp_secret is None
