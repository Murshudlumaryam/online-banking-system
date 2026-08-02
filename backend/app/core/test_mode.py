"""
Shared guard for every debug-only, test-environment-gated endpoint in this
app (OTP capture, admin promotion, ...). Centralizing the check means there
is exactly one place that decides what counts as "test environment", and
exactly one thing to audit to be confident these routes can never activate
in production.
"""
from app.core.config import get_settings


def is_test_environment() -> bool:
    return get_settings().environment == "test"
