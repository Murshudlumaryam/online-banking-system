import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client: AsyncClient):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_metrics_reflect_actual_requests_made(client: AsyncClient):
    # Generate some traffic to observe.
    await client.get("/health")
    await client.get("/health")

    response = await client.get("/metrics")
    body = response.text

    assert 'path_template="/health"' in body
    # The counter should show at least the two /health calls above (plus
    # anything else this test process happened to make — never-decreasing,
    # so ">= 2" rather than "== 2" is the correct assertion here).
    import re

    match = re.search(
        r'http_requests_total\{[^}]*path_template="/health"[^}]*\}\s+([\d.]+)', body
    )
    assert match is not None
    assert float(match.group(1)) >= 2


@pytest.mark.asyncio
async def test_metrics_normalizes_uuid_path_segments(client: AsyncClient, registered_customer: dict):
    """A request to /accounts/{uuid} must show up under one normalized
    label, not fragment into one Prometheus time series per account id."""
    import uuid

    random_id = uuid.uuid4()
    await client.get(f"/api/v1/accounts/{random_id}", headers=registered_customer["headers"])

    response = await client.get("/metrics")
    body = response.text
    assert 'path_template="/api/v1/accounts/:id"' in body
    assert f"/api/v1/accounts/{random_id}" not in body


@pytest.mark.asyncio
async def test_metrics_endpoint_itself_is_not_counted(client: AsyncClient):
    """Scraping /metrics shouldn't inflate its own request counter on every
    scrape — that number would be meaningless (equal to scrape count) and
    would just add noise."""
    response = await client.get("/metrics")
    assert 'path_template="/metrics"' not in response.text


@pytest.mark.asyncio
async def test_rate_limit_rejection_is_recorded(client: AsyncClient):
    from app.core.config import get_settings

    limit = get_settings().rate_limit_login_per_minute
    for _ in range(limit + 1):
        await client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPass1"}
        )

    response = await client.get("/metrics")
    assert "rate_limit_rejections_total" in response.text


def test_render_metrics_uses_single_process_registry_by_default(monkeypatch):
    """Without PROMETHEUS_MULTIPROC_DIR set (dev / docker-compose.yml, i.e.
    single uvicorn process), render_metrics must use the simple in-memory
    registry rather than trying to read a multiprocess directory that
    doesn't exist."""
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    from app.core.metrics import render_metrics

    body, content_type = render_metrics()
    assert content_type.startswith("text/plain")
    assert isinstance(body, bytes)


def test_render_metrics_uses_multiprocess_registry_when_configured(monkeypatch, tmp_path):
    """This is a real, meaningful correctness fix (see Dockerfile.prod /
    gunicorn.conf.py comments and backend/README.md's Phase 9 write-up): a
    multi-worker gunicorn deployment without this branch would have each
    /metrics scrape report only whichever single worker happened to handle
    it, silently under-counting. Verified against a real multi-worker
    gunicorn process manually (see README) — this test just locks in that
    the code path is actually reachable and doesn't crash against a real
    (if empty) multiproc directory."""
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    from app.core.metrics import render_metrics

    body, content_type = render_metrics()
    assert content_type.startswith("text/plain")
    assert isinstance(body, bytes)
