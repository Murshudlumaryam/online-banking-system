from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


def _register_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Kamran",
        "last_name": "Aliyev",
        "date_of_birth": str(date(1990, 1, 1)),
        "phone_number": "+994551112233",
    }


@pytest.mark.asyncio
async def test_login_with_correct_credentials_returns_access_token_and_refresh_cookie(
    client: AsyncClient, unique_email: str
):
    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    # The refresh token must never appear in the JSON body — only as an
    # HttpOnly cookie (see app/modules/auth/cookies.py). A response body
    # leaking it would defeat the entire point of moving it out of
    # localStorage-reachable JavaScript.
    assert "refresh_token" not in body

    refresh_cookie = response.cookies.get("refresh_token")
    assert refresh_cookie, "expected a refresh_token cookie to be set on login"

    # httpx's Cookies object doesn't expose Set-Cookie attributes (httponly/
    # secure/samesite) directly — assert on the raw Set-Cookie header instead.
    set_cookie_header = response.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=strict" in set_cookie_header.lower()
    assert "path=/api/v1/auth" in set_cookie_header.lower()


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client: AsyncClient, unique_email: str):
    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "WrongPass1"}
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_for_unknown_email_returns_401_not_404(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "StrongPass1"}
    )
    # Deliberately 401, not 404 — prevents user enumeration.
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_blocked_user_cannot_login(
    client: AsyncClient, db_session: AsyncSession, unique_email: str
):
    await client.post("/api/v1/auth/register", json=_register_payload(unique_email))

    result = await db_session.execute(select(User).where(User.email == unique_email.lower()))
    user = result.scalar_one()
    user.is_blocked = True
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "StrongPass1"}
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "USER_BLOCKED"
