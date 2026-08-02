import pytest
from httpx import AsyncClient

from app.db.session import check_db_connection, check_redis_connection


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_endpoint_reports_db_and_redis(client: AsyncClient):
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "database" in body
    assert "redis" in body


@pytest.mark.asyncio
async def test_check_db_connection_returns_false_for_unreachable_database():
    # A syntactically valid but unroutable URL — the connection attempt
    # itself must fail, and the helper must swallow that into `False` rather
    # than raising (so /ready never 500s just because the DB is briefly down).
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.db.session as session_module

    original_engine = session_module.engine
    session_module.engine = create_async_engine(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nonexistent"
    )
    try:
        assert await check_db_connection() is False
    finally:
        await session_module.engine.dispose()
        session_module.engine = original_engine


@pytest.mark.asyncio
async def test_check_redis_connection_returns_false_for_unreachable_redis():
    assert await check_redis_connection("redis://127.0.0.1:1/0") is False


@pytest.mark.asyncio
async def test_check_redis_connection_returns_true_for_reachable_redis():
    assert await check_redis_connection("redis://127.0.0.1:6379/0") is True
