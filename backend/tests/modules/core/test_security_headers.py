import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present_on_every_response(client: AsyncClient):
    response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in response.headers["permissions-policy"]
    assert "max-age" in response.headers["strict-transport-security"]
    assert response.headers["cross-origin-opener-policy"] == "same-origin"


@pytest.mark.asyncio
async def test_request_id_header_present_and_echoed(client: AsyncClient):
    response = await client.get("/health", headers={"X-Request-ID": "my-custom-id-123"})
    assert response.headers["x-request-id"] == "my-custom-id-123"


@pytest.mark.asyncio
async def test_request_id_generated_when_not_provided(client: AsyncClient):
    response = await client.get("/health")
    assert response.headers["x-request-id"]  # non-empty, server-generated
