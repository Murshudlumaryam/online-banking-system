"""
Rate limiter backends.

`RedisRateLimiter` is the production backend — a fixed-window counter using
Redis INCR + EXPIRE, which works correctly across multiple backend worker
processes (an in-memory limiter would not: each worker tracks its own
counters, silently multiplying the effective limit by the worker count).

Construction is synchronous and lazy (redis-py does not open a connection
until the first command), so the backend can be created directly inside
`create_app()` without needing an async startup step. If Redis is briefly
unreachable at request time, the limiter fails OPEN (allows the request) and
logs a warning — rate limiting is a defense-in-depth control, not something
that should take the whole API down if Redis has a hiccup.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Protocol

from redis.asyncio import Redis

logger = logging.getLogger("app.rate_limiter")


class RateLimiterBackend(Protocol):
    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    """Zero-dependency fallback for local development without Redis."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        self._redis: Redis = Redis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        try:
            # INCR creates the key at 1 if absent; only the request that
            # created it sets the expiry, so the window is fixed from the
            # first-hit time (simple, sufficiently accurate fixed-window
            # counter — not a sliding-log, which is fine for this use case).
            current = int(await self._redis.incr(key))
            if current == 1:
                await self._redis.expire(key, window_seconds)
            return current <= limit
        except Exception:
            logger.warning("rate_limiter_redis_unavailable_failing_open", extra={"key": key})
            return True

    async def close(self) -> None:
        await self._redis.aclose()
