"""
Email delivery backends (Phase 7).

`ConsoleEmailProvider` is the safe default — it logs the email instead of
sending it, exactly matching the Phase 1-6 "log-only stub" behavior, and
requires no external configuration. `SMTPEmailProvider` performs a real send
via any standard SMTP server (SendGrid, SES, Postmark, a corporate relay,
etc. all speak SMTP) using `aiosmtplib`. Switch between them with the
`EMAIL_BACKEND` setting — no code changes needed to go from dev to
production once real SMTP credentials are available.
"""
import logging
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings

logger = logging.getLogger("app.email")


class EmailProvider(Protocol):
    async def send(self, *, to_address: str, subject: str, body: str) -> None: ...


class ConsoleEmailProvider:
    """Logs the email instead of sending it. Never logs full body content
    that might contain sensitive data (OTP codes, reset tokens) — only
    metadata, consistent with the app's logging policy elsewhere."""

    async def send(self, *, to_address: str, subject: str, body: str) -> None:
        from app.core.metrics import notification_delivery_total

        logger.info(
            "email_dispatched_console_backend",
            extra={"to_address": to_address, "subject": subject, "body_length": len(body)},
        )
        notification_delivery_total.labels(channel="email", outcome="success").inc()


class SMTPEmailProvider:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address

    async def send(self, *, to_address: str, subject: str, body: str) -> None:
        from app.core.metrics import notification_delivery_total

        message = EmailMessage()
        message["From"] = self._from_address
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
                start_tls=self._use_tls,
            )
        except Exception:
            notification_delivery_total.labels(channel="email", outcome="failure").inc()
            logger.error("email_delivery_failed", extra={"to_address": to_address}, exc_info=True)
            raise
        notification_delivery_total.labels(channel="email", outcome="success").inc()


def create_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.email_backend == "smtp":
        return SMTPEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_address=settings.smtp_from_address,
        )
    return ConsoleEmailProvider()
