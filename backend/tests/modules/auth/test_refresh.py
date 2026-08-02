from datetime import date

import pytest
from httpx import AsyncClient


def _register_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "first_name": "Nigar",
        "last_name": "Huseynova",
        "date_of_birth": str(date(1992, 3, 15)),
        "phone_number": "+994701112233",
    }


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/api/v1/auth/register", json=_register_payload(email))
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass1"}
    )
    return response.json()


@pytest.mark.asyncio
async def test_refresh_rotates_token_pair(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert new_tokens["access_token"] != tokens["access_token"]


@pytest.mark.asyncio
async def test_reusing_a_rotated_refresh_token_is_rejected(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)

    first_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first_refresh.status_code == 200

    # Reusing the same (now-rotated) refresh token must fail.
    second_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert second_refresh.status_code == 401
    assert second_refresh.json()["error_code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_the_new_token_too(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)

    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    new_refresh_token = rotated.json()["refresh_token"]

    # Trigger reuse detection on the original token.
    await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    # The rotated token that came from that family should now also be revoked.
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh_token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient, unique_email: str):
    tokens = await _register_and_login(client, unique_email)

    logout_response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_token_is_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert response.status_code == 401
