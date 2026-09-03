"""Tests for the Frankfurter live exchange rate client and the
GET /admin/exchange-rates/live preview endpoint."""
import httpx
import pytest

from app.modules.exchange_rates.frankfurter_client import (
    ExchangeRateProviderError,
    fetch_live_rate,
)


def _mocked_client(handler):
    real_async_client = httpx.AsyncClient

    class _MockedAsyncClient(real_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    return _MockedAsyncClient


@pytest.mark.asyncio
async def test_fetch_live_rate_returns_the_requested_pair(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["base"] == "AZN"
        assert request.url.params["symbols"] == "USD"
        return httpx.Response(200, json={"amount": 1.0, "base": "AZN", "date": "2026-09-01", "rates": {"USD": 0.588}})

    monkeypatch.setattr(httpx, "AsyncClient", _mocked_client(handler))

    rate = await fetch_live_rate(source_currency="azn", target_currency="usd")
    assert rate == 0.588


@pytest.mark.asyncio
async def test_fetch_live_rate_raises_a_clean_error_when_pair_is_missing(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"amount": 1.0, "base": "AZN", "date": "2026-09-01", "rates": {}})

    monkeypatch.setattr(httpx, "AsyncClient", _mocked_client(handler))

    with pytest.raises(ExchangeRateProviderError):
        await fetch_live_rate(source_currency="AZN", target_currency="XYZ")


@pytest.mark.asyncio
async def test_fetch_live_rate_raises_a_clean_error_on_http_failure(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "AsyncClient", _mocked_client(handler))

    with pytest.raises(ExchangeRateProviderError):
        await fetch_live_rate(source_currency="AZN", target_currency="USD")


@pytest.mark.asyncio
async def test_admin_can_preview_a_live_rate(client, admin_headers, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"amount": 1.0, "base": "AZN", "date": "2026-09-01", "rates": {"USD": 0.588}})

    monkeypatch.setattr(httpx, "AsyncClient", _mocked_client(handler))

    response = await client.get(
        "/api/v1/admin/exchange-rates/live",
        params={"source_currency": "AZN", "target_currency": "USD"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_currency"] == "AZN"
    assert body["target_currency"] == "USD"
    assert body["rate"] == "0.588"


@pytest.mark.asyncio
async def test_normal_user_cannot_preview_a_live_rate(client, registered_customer):
    response = await client.get(
        "/api/v1/admin/exchange-rates/live",
        params={"source_currency": "AZN", "target_currency": "USD"},
        headers=registered_customer["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_provider_failure_returns_a_clean_502_not_a_500(client, admin_headers, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "AsyncClient", _mocked_client(handler))

    response = await client.get(
        "/api/v1/admin/exchange-rates/live",
        params={"source_currency": "AZN", "target_currency": "USD"},
        headers=admin_headers,
    )
    assert response.status_code == 502
