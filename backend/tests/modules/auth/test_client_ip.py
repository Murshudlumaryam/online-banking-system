"""
Regression tests for a real IP-spoofing gap found during the audit-log
production-readiness pass: get_client_ip used to trust X-Forwarded-For
unconditionally, letting any client write an arbitrary IP into the audit
trail. Now gated by TRUST_PROXY_HEADERS (default False) and, when
enabled, reads the last hop rather than the first — see that function's
docstring for why the first entry still isn't safe even behind a real
reverse proxy that appends instead of overwriting.
"""
from unittest.mock import MagicMock

import pytest

from app.modules.auth.dependencies import get_client_ip


def _make_request(headers: dict, client_host: str | None = "198.51.100.9"):
    request = MagicMock()
    request.headers = headers
    request.client = MagicMock(host=client_host) if client_host else None
    return request


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_x_forwarded_for_is_ignored_by_default(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    request = _make_request({"X-Forwarded-For": "203.0.113.66"}, client_host="198.51.100.9")
    assert get_client_ip(request) == "198.51.100.9"


def test_x_forwarded_for_is_honored_when_trust_proxy_headers_enabled(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    request = _make_request({"X-Forwarded-For": "203.0.113.66"})
    assert get_client_ip(request) == "203.0.113.66"


def test_last_hop_is_used_not_the_client_supplied_first_one(monkeypatch):
    """A client that pre-sets its own X-Forwarded-For before a proxy that
    *appends* (Caddy's default) ends up with the attacker's fake IP first
    and the proxy's real observed IP last — the last one is the only part
    of this header a single-hop deployment can actually vouch for."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    request = _make_request({"X-Forwarded-For": "1.2.3.4, 198.51.100.9"})
    assert get_client_ip(request) == "198.51.100.9"


def test_no_client_and_no_header_returns_none(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    request = _make_request({}, client_host=None)
    assert get_client_ip(request) is None
