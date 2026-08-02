"""
Test-only OTP capture (Phase 8 / e2e testing support).

Real OTP codes are never logged or exposed through any normal API response —
that's a hard security requirement elsewhere in this codebase. But an
automated end-to-end test driving the real UI has no SMS/email inbox to
read from, so it needs *some* way to complete the OTP-confirmation step.

The pattern here (a debug-only capture store, gated by `ENVIRONMENT=test`)
mirrors what many real fintechs do for exactly this problem — never enabled
outside test, never touches production data paths, and the values are held
in a plain process-local dict that's wiped whenever the process restarts.
"""
import uuid

from app.core.test_mode import is_test_environment

# Bounded so a long-running test process can't leak memory — old entries are
# simply evicted once the cap is hit, which is fine since e2e tests consume
# the code within seconds of it being generated.
_MAX_ENTRIES = 200
_store: dict[uuid.UUID, str] = {}


def is_enabled() -> bool:
    return is_test_environment()


def capture(transaction_id: uuid.UUID, otp_code: str) -> None:
    if not is_enabled():
        return
    if len(_store) >= _MAX_ENTRIES:
        _store.pop(next(iter(_store)))
    _store[transaction_id] = otp_code


def pop(transaction_id: uuid.UUID) -> str | None:
    """Read-once: returns the code and removes it, same as a real OTP inbox message being consumed."""
    return _store.pop(transaction_id, None)
