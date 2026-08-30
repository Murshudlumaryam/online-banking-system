"""
Async SQLAlchemy engine/session setup (asyncpg driver).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# A second engine, deliberately *not* pooled, for use only inside Celery
# task bodies (see app/background_tasks/tasks.py). Those tasks are plain
# synchronous Celery functions that call `asyncio.run(...)` to run their
# async logic — and asyncio.run() creates a brand-new event loop on every
# single invocation. asyncpg connections are bound to the event loop they
# were opened under; if `engine` above's pool hands out a connection that
# was established during an earlier asyncio.run() call, the next call's
# (new, different) event loop can't use it and asyncpg raises
# "attached to a different loop". This was found by actually running a
# worker under load and reading its error log, not by inspecting the
# code — the failure is intermittent (only once the pool has something to
# reuse) and every test that only exercised a single audit write in
# isolation would never trigger it.
#
# NullPool means every asyncio.run() call opens a fresh connection and
# closes it when that call's event loop closes — no connection ever
# survives to be reused under a different loop. The web app's engine
# above is unaffected (uvicorn's event loop is a single long-lived loop
# for the whole process, so pooling is safe and desirable there).
celery_engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    poolclass=NullPool,
)

CelerySessionLocal = async_sessionmaker(
    bind=celery_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """Used by the /ready endpoint."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis_connection(redis_url: str) -> bool:
    """Used by the /ready endpoint."""
    from redis.asyncio import Redis

    try:
        client: Redis = Redis.from_url(redis_url, socket_timeout=1.0)
        result = await client.ping()
        await client.aclose()
        return bool(result)
    except Exception:
        return False
