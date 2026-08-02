from datetime import date

import pytest
from httpx import AsyncClient

from app.core.security import create_password_reset_token


def _register_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Elvin",
        "last_name": "Guliyev",
        "date_of_birth": str(date(1988, 7, 4)),
        "phone_number": "+994121112233",
    }


@pytest.mark.asyncio
async def test_change_password_requires_correct_current_password(
    client: AsyncClient, unique_email: str
):
    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    bad_response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "WrongPass1", "new_password": "NewStrongPass1"},
        headers=headers,
    )
    assert bad_response.status_code == 401

    good_response = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "StrongPass1", "new_password": "NewStrongPass1"},
        headers=headers,
    )
    assert good_response.status_code == 204

    # Old password no longer works, new one does.
    old_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "NewStrongPass1"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_password_change_revokes_existing_refresh_tokens(
    client: AsyncClient, unique_email: str
):
    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "StrongPass1", "new_password": "NewStrongPass1"},
        headers=headers,
    )

    refresh_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_request_does_not_reveal_user_existence(
    client: AsyncClient, unique_email: str
):
    response = await client.post(
        "/api/v1/auth/password/reset-request", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 204  # same response whether or not the email exists

    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))
    response = await client.post(
        "/api/v1/auth/password/reset-request", json={"email": unique_email}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_password_reset_confirm_with_valid_token(client: AsyncClient, db_session, unique_email: str):
    from sqlalchemy import select

    from app.modules.users.models import User

    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()
    reset_token = create_password_reset_token(user_id=user.id, current_password_hash=user.password_hash)

    confirm_response = await client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"reset_token": reset_token, "new_password": "ResetStrongPass1"},
    )
    assert confirm_response.status_code == 204

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "ResetStrongPass1"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_token_cannot_be_reused(client: AsyncClient, db_session, unique_email: str):
    from sqlalchemy import select

    from app.modules.users.models import User

    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()
    reset_token = create_password_reset_token(user_id=user.id, current_password_hash=user.password_hash)

    first = await client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"reset_token": reset_token, "new_password": "ResetStrongPass1"},
    )
    assert first.status_code == 204

    # Same token again — the password hash has changed, so the embedded
    # fingerprint no longer matches.
    second = await client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"reset_token": reset_token, "new_password": "AnotherStrongPass1"},
    )
    assert second.status_code == 401
    assert second.json()["error_code"] == "INVALID_RESET_TOKEN"
