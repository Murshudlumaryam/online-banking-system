"""
Request-scoped middleware: correlation ID injection, rate limiting, and
security headers.

Implemented as pure ASGI middleware (not BaseHTTPMiddleware) deliberately.
BaseHTTPMiddleware wraps each request in an anyio TaskGroup; exceptions
raised deep in the call stack get wrapped in an ExceptionGroup that bypasses
FastAPI's registered `@app.exception_handler` machinery, so unhandled errors
leak out as raw tracebacks instead of the uniform ErrorResponse envelope.
Plain ASGI middleware does not have this problem.
"""
import json
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.rate_limiter import RateLimiterBackend


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_wrapper)


class SecurityHeadersMiddleware:
    """
    Adds baseline OWASP-recommended response headers. TLS termination (and
    therefore the meaningful enforcement of Strict-Transport-Security) is
    expected to happen at a reverse proxy in front of this service; the
    header is still safe to send over plain HTTP (browsers ignore it there).
    """

    _HEADERS = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
        (b"strict-transport-security", b"max-age=63072000; includeSubDomains"),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].extend(self._HEADERS)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """
    Applies a per-window request limit to configured path prefixes, backed by
    a pluggable `RateLimiterBackend` (Redis in production; see
    app.core.rate_limiter). Each prefix maps to (limit, window_seconds).
    """

    def __init__(self, app: ASGIApp, backend: RateLimiterBackend, limits: dict[str, tuple[int, int]]):
        self.app = app
        self._backend = backend
        self._limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        for prefix, (limit, window_seconds) in self._limits.items():
            if path.startswith(prefix):
                key = f"ratelimit:{prefix}:{client_ip}"
                allowed = await self._backend.is_allowed(key, limit, window_seconds)
                if not allowed:
                    from app.core.metrics import rate_limit_rejections_total

                    rate_limit_rejections_total.labels(path_prefix=prefix).inc()
                    await self._send_rate_limited(send)
                    return
                break

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_rate_limited(send: Send) -> None:
        body = json.dumps(
            {
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests — please try again later",
                "details": [],
                "request_id": str(uuid.uuid4()),
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


_ID_SEGMENT_PATTERN = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _normalize_path_template(path: str) -> str:
    """Collapses UUID path segments to `/:id` so metrics don't get a new
    label (and Prometheus time series) per distinct account/transaction/etc.
    e.g. `/api/v1/accounts/3fa8.../balance` -> `/api/v1/accounts/:id/balance`."""
    return _ID_SEGMENT_PATTERN.sub("/:id", path)


class MetricsMiddleware:
    """Records request count and latency for every HTTP request, exposed at
    `GET /metrics` in Prometheus format (see app/core/metrics.py and main.py)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from app.core.metrics import http_request_duration_seconds, http_requests_total

        method = scope.get("method", "UNKNOWN")
        path_template = _normalize_path_template(scope.get("path", ""))
        start = time.monotonic()
        status_code_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # /metrics itself is excluded so scraping Prometheus doesn't
            # inflate its own metrics on every scrape.
            if path_template != "/metrics":
                duration = time.monotonic() - start
                http_requests_total.labels(
                    method=method, path_template=path_template, status_code=status_code_holder["code"]
                ).inc()
                http_request_duration_seconds.labels(method=method, path_template=path_template).observe(
                    duration
                )
