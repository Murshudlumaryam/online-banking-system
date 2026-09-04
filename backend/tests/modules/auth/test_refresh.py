import uuid
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
        "national_id": f"TEST{uuid.uuid4().hex[:12].upper()}",
    }


async def _register_and_login(client: AsyncClient, email: str, stub_background_tasks) -> dict:
    """Registers, logs in, and returns the login response body. The refresh
    token itself is never in that body (see test_login.py) — it's captured
    from the response cookie by the caller when a test needs to manipulate
    it directly (e.g. to test reuse detection)."""
    from tests.conftest import register_and_confirm

    await register_and_confirm(client, stub_background_tasks, _register_payload(email))
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass1"}
    )
    return response


@pytest.mark.asyncio
async def test_refresh_rotates_token_pair(client: AsyncClient, unique_email: str, stub_background_tasks):
    login_response = await _register_and_login(client, unique_email, stub_background_tasks)
    original_access_token = login_response.json()["access_token"]
    original_refresh_cookie = login_response.cookies.get("refresh_token")

    # httpx's AsyncClient automatically resends cookies it received, so this
    # call carries the refresh_token cookie set by login without us doing
    # anything extra — exactly mirroring how a real browser behaves.
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    body = response.json()
    assert "refresh_token" not in body
    assert body["access_token"] != original_access_token

    new_refresh_cookie = response.cookies.get("refresh_token")
    assert new_refresh_cookie
    assert new_refresh_cookie != original_refresh_cookie


@pytest.mark.asyncio
async def test_reusing_a_rotated_refresh_token_is_rejected(client: AsyncClient, unique_email: str, stub_background_tasks):
    login_response = await _register_and_login(client, unique_email, stub_background_tasks)
    original_refresh_cookie = login_response.cookies.get("refresh_token")

    first_refresh = await client.post("/api/v1/auth/refresh")
    assert first_refresh.status_code == 200
    # The client's cookie jar now holds the *new* (rotated) token. To prove
    # the *old* one is really dead, we have to put it back explicitly —
    # otherwise this request would just reuse the already-valid new one and
    # the test would pass for the wrong reason.
    client.cookies.set("refresh_token", original_refresh_cookie, path="/api/v1/auth")

    second_refresh = await client.post("/api/v1/auth/refresh")
    assert second_refresh.status_code == 401
    assert second_refresh.json()["error_code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_the_new_token_too(client: AsyncClient, unique_email: str, stub_background_tasks):
    login_response = await _register_and_login(client, unique_email, stub_background_tasks)
    original_refresh_cookie = login_response.cookies.get("refresh_token")

    rotated = await client.post("/api/v1/auth/refresh")
    new_refresh_cookie = rotated.cookies.get("refresh_token")

    # Trigger reuse detection on the original (now-stale) token.
    client.cookies.set("refresh_token", original_refresh_cookie, path="/api/v1/auth")
    await client.post("/api/v1/auth/refresh")

    # The rotated token that came from that same family should now also be
    # revoked, even though it was never itself reused — reuse detection
    # revokes the whole family, not just the specific reused token.
    client.cookies.set("refresh_token", new_refresh_cookie, path="/api/v1/auth")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient, unique_email: str, stub_background_tasks):
    login_response = await _register_and_login(client, unique_email, stub_background_tasks)
    original_refresh_cookie = login_response.cookies.get("refresh_token")

    logout_response = await client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    # Force the (now-revoked) original token back onto the client in case
    # logout's Set-Cookie deletion already cleared it from the jar — the
    # point of this test is that the *token* is revoked server-side, not
    # merely that the cookie is gone from this particular client.
    client.cookies.set("refresh_token", original_refresh_cookie, path="/api/v1/auth")
    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_without_a_cookie_is_rejected(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_token_cookie_is_rejected(client: AsyncClient):
    client.cookies.set("refresh_token", "not-a-real-token", path="/api/v1/auth")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
