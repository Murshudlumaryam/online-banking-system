import asyncio

import pytest
from httpx import AsyncClient

from app.core.rate_limiter import InMemoryRateLimiter, RedisRateLimiter


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_allows_up_to_limit():
    limiter = InMemoryRateLimiter()
    key = "test:in-memory:1"

    results = [await limiter.is_allowed(key, limit=3, window_seconds=60) for _ in range(3)]
    assert results == [True, True, True]

    # The 4th request within the same window is rejected.
    assert await limiter.is_allowed(key, limit=3, window_seconds=60) is False


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_keys_are_independent():
    limiter = InMemoryRateLimiter()
    assert await limiter.is_allowed("key-a", limit=1, window_seconds=60) is True
    assert await limiter.is_allowed("key-a", limit=1, window_seconds=60) is False
    # A different key has its own independent budget.
    assert await limiter.is_allowed("key-b", limit=1, window_seconds=60) is True


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_window_expires():
    limiter = InMemoryRateLimiter()
    key = "test:in-memory:window"

    assert await limiter.is_allowed(key, limit=1, window_seconds=0) is True
    await asyncio.sleep(0.01)
    # With a zero-second window, the previous hit should already have aged out.
    assert await limiter.is_allowed(key, limit=1, window_seconds=0) is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_allows_up_to_limit_and_then_denies():
    limiter = RedisRateLimiter("redis://127.0.0.1:6379/1")
    key = "test:redis:1"
    try:
        assert await limiter.is_allowed(key, limit=2, window_seconds=60) is True
        assert await limiter.is_allowed(key, limit=2, window_seconds=60) is True
        assert await limiter.is_allowed(key, limit=2, window_seconds=60) is False
    finally:
        # Clean up the key so this test is independently re-runnable.
        await limiter._redis.delete(key)
        await limiter.close()


@pytest.mark.asyncio
async def test_redis_rate_limiter_fails_open_when_redis_unreachable():
    # Port 1 is essentially guaranteed to refuse the connection immediately.
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0")
    try:
        # Must not raise, and must fail OPEN (allow) rather than blocking traffic.
        assert await limiter.is_allowed("test:unreachable", limit=1, window_seconds=60) is True
    finally:
        await limiter.close()


@pytest.mark.asyncio
async def test_login_endpoint_enforces_rate_limit(client: AsyncClient):
    from app.core.config import get_settings

    limit = get_settings().rate_limit_login_per_minute

    responses = []
    for _ in range(limit + 1):
        response = await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPass1"}
        )
        responses.append(response.status_code)

    # The first `limit` requests are processed normally (401 — wrong credentials);
    # only the request that exceeds the budget gets 429.
    assert responses[:-1] == [401] * limit
    assert responses[-1] == 429
