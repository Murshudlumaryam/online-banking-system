"""
Regression tests for app.core.logging.JsonFormatter.

Found during an OTP-delivery audit: the formatter only forwarded a fixed
allowlist of `extra` keys ("request_id", "user_id", "error_code", "path",
"module"), silently dropping anything else — including the transaction_id/
channel fields added to the transfer-OTP audit trail. Structured logging
that silently discards the fields you actually asked it to log is worse
than no logging at all, since it looks like it's working.
"""
import json
import logging

from app.core.logging import JsonFormatter


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_arbitrary_extra_fields_are_included():
    record = logging.LogRecord(
        name="app.otp", level=logging.INFO, pathname="service.py", lineno=1,
        msg="TRANSFER_OTP_SEND_REQUESTED", args=(), exc_info=None,
    )
    record.transaction_id = "abc-123"
    record.channel = "email"

    payload = _format(record)
    assert payload["transaction_id"] == "abc-123"
    assert payload["channel"] == "email"
    assert payload["message"] == "TRANSFER_OTP_SEND_REQUESTED"


def test_previously_supported_fields_still_work():
    """The original fixed allowlist — kept working for backward compatibility."""
    record = logging.LogRecord(
        name="app.errors", level=logging.WARNING, pathname="x.py", lineno=1,
        msg="domain_error", args=(), exc_info=None,
    )
    record.request_id = "req-1"
    record.user_id = "user-1"
    record.error_code = "INVALID_CREDENTIALS"
    record.path = "/api/v1/auth/login"

    payload = _format(record)
    assert payload["request_id"] == "req-1"
    assert payload["user_id"] == "user-1"
    assert payload["error_code"] == "INVALID_CREDENTIALS"
    assert payload["path"] == "/api/v1/auth/login"


def test_module_is_always_included_even_though_it_is_a_standard_attribute():
    record = logging.LogRecord(
        name="app.errors", level=logging.INFO, pathname="/app/exceptions.py", lineno=1,
        msg="something happened", args=(), exc_info=None,
    )
    payload = _format(record)
    assert payload["module"] == "exceptions"


def test_python_internal_record_bookkeeping_is_not_leaked():
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname="x.py", lineno=42,
        msg="hello", args=(), exc_info=None,
    )
    payload = _format(record)
    unexpected_keys = {"levelno", "pathname", "lineno", "thread", "process", "args", "msg", "relativeCreated"}
    assert not (unexpected_keys & payload.keys())


def test_none_valued_extra_fields_are_omitted():
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    record.optional_field = None
    payload = _format(record)
    assert "optional_field" not in payload


def test_otp_code_is_never_a_field_name_used_anywhere_in_the_transfer_otp_logging():
    import inspect

    from app.modules.transactions import service as transactions_service

    source = inspect.getsource(transactions_service)
    otp_log_lines = [line for line in source.splitlines() if "logger." in line and "OTP" in line.upper()]
    assert otp_log_lines, "expected to find at least one OTP-related log call to check"
    for line in otp_log_lines:
        assert "otp_code" not in line
