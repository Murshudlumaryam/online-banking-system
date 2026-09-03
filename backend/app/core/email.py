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
import httpx

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
            logger.exception("email_delivery_failed", extra={"to_address": to_address})
            raise
        notification_delivery_total.labels(channel="email", outcome="success").inc()


class ResendEmailProvider:
    """
    Sends via the Resend (https://resend.com) REST API — one HTTP POST,
    no SMTP server/port/TLS configuration needed. Good fit for a project
    like this one: a free tier that reaches a real inbox (Gmail included)
    without a paid SMTP relay, which is exactly the gap that caused the
    original "OTP never reaches Gmail" symptom (see ROOT_CAUSE_REPORT.md
    — EMAIL_BACKEND defaulted to console, and even switched to "smtp"
    there was no free provider readily available). Plain text body only,
    matching every other provider here (OTP/reset-link content doesn't
    need HTML).
    """

    _API_URL = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from_address = from_address

    async def send(self, *, to_address: str, subject: str, body: str) -> None:
        from app.core.metrics import notification_delivery_total

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "from": self._from_address,
                        "to": to_address,
                        "subject": subject,
                        # text, not html — see class docstring. Resend
                        # requires *some* body; plain text is sent as-is.
                        "text": body,
                    },
                )
                response.raise_for_status()
        except Exception:
            notification_delivery_total.labels(channel="email", outcome="failure").inc()
            logger.exception("email_delivery_failed", extra={"to_address": to_address, "provider": "resend"})
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
    if settings.email_backend == "resend":
        return ResendEmailProvider(
            api_key=settings.resend_api_key,
            from_address=settings.resend_from_address,
        )
    return ConsoleEmailProvider()
