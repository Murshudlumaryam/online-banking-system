from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    MetricsMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limiter import (
    InMemoryRateLimiter,
    RateLimiterBackend,
    RedisRateLimiter,
)
from app.db.session import check_db_connection, check_redis_connection
from app.modules.accounts.router import router as accounts_router
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.beneficiaries.router import router as beneficiaries_router
from app.modules.cards.router import router as cards_router
from app.modules.customers.router import router as customers_router
from app.modules.exchange_rates.router import router as exchange_rates_router
from app.modules.scheduled_payments.router import router as scheduled_payments_router
from app.modules.transactions.router import router as transactions_router

settings = get_settings()

OPENAPI_TAGS = [
    {"name": "auth", "description": "Registration, login, token refresh, and password management."},
    {"name": "customers", "description": "The signed-in customer's own profile and dashboard."},
    {"name": "accounts", "description": "The signed-in customer's own bank accounts (read-only)."},
    {"name": "cards", "description": "The signed-in customer's own cards (read-only, masked PAN)."},
    {"name": "beneficiaries", "description": "Saved payees for faster future transfers."},
    {"name": "exchange-rates", "description": "Currently active currency conversion rates."},
    {"name": "transactions", "description": "Money transfers: initiate, confirm via OTP, list, search."},
    {"name": "scheduled-payments", "description": "Recurring/standing transfer authorizations, executed automatically without interactive OTP."},
    {"name": "admin", "description": "Back-office operations. Requires the ADMIN role."},
    {"name": "system", "description": "Liveness/readiness probes for orchestration and monitoring."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(environment=settings.environment)
    yield
    rate_limiter = getattr(app.state, "rate_limiter", None)
    if isinstance(rate_limiter, RedisRateLimiter):
        await rate_limiter.close()


def _build_rate_limits() -> dict[str, tuple[int, int]]:
    """
    Maps path prefix -> (limit, window_seconds). Order matters: the
    middleware uses the first matching prefix, so more specific auth
    sub-paths must be listed before the general "/auth" fallback.
    """
    prefix = settings.api_v1_prefix
    return {
        f"{prefix}/auth/login": (settings.rate_limit_login_per_minute, 60),
        f"{prefix}/auth/register": (settings.rate_limit_register_per_minute, 60),
        f"{prefix}/auth/password/reset-request": (settings.rate_limit_password_reset_per_minute, 60),
        f"{prefix}/auth": (settings.rate_limit_login_per_minute, 60),  # refresh/logout/change-password
        f"{prefix}/transactions/transfer": (settings.rate_limit_transfer_per_minute, 60),
        prefix: (settings.rate_limit_default_per_minute, 60),
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        description=(
            "Enterprise-grade online banking platform — REST API.\n\n"
            "Authenticate via `POST /api/v1/auth/login`, then use the returned "
            "`access_token` as a Bearer token (click **Authorize** below)."
        ),
        contact={"name": "Platform Engineering", "email": "engineering@example-bank.internal"},
        license_info={"name": "Proprietary — internal use only"},
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    if settings.rate_limit_backend == "redis":
        rate_limiter: RateLimiterBackend = RedisRateLimiter(settings.redis_url)
    else:
        rate_limiter = InMemoryRateLimiter()
    app.state.rate_limiter = rate_limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    if settings.metrics_enabled:
        app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware, backend=rate_limiter, limits=_build_rate_limits())

    register_exception_handlers(app)

    app.include_router(auth_router)
    app.include_router(customers_router)
    app.include_router(accounts_router)
    app.include_router(cards_router)
    app.include_router(beneficiaries_router)
    app.include_router(exchange_rates_router)
    app.include_router(transactions_router)
    app.include_router(scheduled_payments_router)
    app.include_router(admin_router)

    @app.get("/health", tags=["system"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"], summary="Readiness probe (checks DB and Redis connectivity)")
    async def ready() -> dict:
        db_ok = await check_db_connection()
        redis_ok = await check_redis_connection(settings.redis_url)
        overall_ok = db_ok and redis_ok
        return {
            "status": "ok" if overall_ok else "degraded",
            "database": db_ok,
            "redis": redis_ok,
        }

    if settings.metrics_enabled:

        @app.get(
            "/metrics",
            tags=["system"],
            summary="Prometheus metrics (text exposition format)",
            include_in_schema=False,
        )
        async def metrics() -> Response:
            from app.core.metrics import render_metrics

            body, content_type = render_metrics()
            return Response(content=body, media_type=content_type)

    return app


app = create_app()
