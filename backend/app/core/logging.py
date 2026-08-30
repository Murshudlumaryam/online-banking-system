"""
Structured (JSON) logging configuration.

Never log: passwords, tokens, full card numbers, CVV, OTP codes. This module
only configures format/output; call sites are responsible for not passing
sensitive values into `extra`.
"""
import json
import logging
import sys
from datetime import datetime, timezone

# Every attribute a plain logging.LogRecord carries regardless of what the
# call site passed via `extra=` — used to separate "real" extra fields from
# Python's own bookkeeping. Computed from a throwaway record rather than
# hardcoded, so it stays correct if the stdlib ever adds an attribute.
#
# "module" is deliberately NOT excluded even though it's a standard,
# auto-computed attribute (the calling file's module name) — the previous
# version of this formatter explicitly surfaced it in every log line, and
# dropping it would be a silent regression for anyone grepping logs by
# module.
_STANDARD_LOG_RECORD_ATTRS = (
    frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}
) - {"module"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Every field passed via `extra={...}` at the call site, not just a
        # fixed allowlist — a previous version of this formatter only
        # forwarded ("request_id", "user_id", "error_code", "path",
        # "module"), which silently dropped anything else (e.g. the
        # transaction_id/channel fields added to the transfer-OTP audit
        # trail — found by actually reading the resulting log output, not
        # just reviewing the logging call sites).
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_ATTRS or key in payload:
                continue
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, environment: str) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if environment != "production" else logging.INFO)

    # Quiet down noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
