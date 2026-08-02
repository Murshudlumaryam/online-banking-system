"""
SMS delivery backends (Phase 8).

Mirrors app.core.email's design: `ConsoleSMSProvider` is the safe default
(logs instead of sending), `TwilioSMSProvider` performs a real send via
Twilio's REST API. We talk to Twilio's plain HTTP API directly with httpx
rather than pulling in the official `twilio` SDK — the API surface we need
(one POST to the Messages resource) is small enough that a hand-rolled
client is easier to audit and has one fewer third-party dependency in the
security-sensitive path that handles OTP codes.

Reference: https://www.twilio.com/docs/sms/api/message-resource#create-a-message-resource
"""
import logging
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.sms")


class SMSDeliveryError(Exception):
    """Raised when the SMS provider rejects or fails to send a message."""


class SMSProvider(Protocol):
    async def send(self, *, to_number: str, body: str) -> None: ...


class ConsoleSMSProvider:
    """Logs the SMS instead of sending it. Never logs the message body —
    OTP codes and other sensitive content must never hit application logs,
    consistent with the app's logging policy elsewhere."""

    async def send(self, *, to_number: str, body: str) -> None:
        from app.core.metrics import notification_delivery_total

        logger.info(
            "sms_dispatched_console_backend",
            extra={"to_number": to_number, "body_length": len(body)},
        )
        notification_delivery_total.labels(channel="sms", outcome="success").inc()


class TwilioSMSProvider:
    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        api_base_url: str = "https://api.twilio.com",
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._api_base_url = api_base_url.rstrip("/")

    async def send(self, *, to_number: str, body: str) -> None:
        from app.core.metrics import notification_delivery_total

        url = f"{self._api_base_url}/2010-04-01/Accounts/{self._account_sid}/Messages.json"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    auth=(self._account_sid, self._auth_token),
                    data={"To": to_number, "From": self._from_number, "Body": body},
                )

            if response.status_code >= 400:
                # Twilio's error body is JSON: {"code": ..., "message": ..., "more_info": ...}
                try:
                    detail = response.json().get("message", response.text)
                except ValueError:
                    detail = response.text
                raise SMSDeliveryError(
                    f"Twilio rejected the message (HTTP {response.status_code}): {detail}"
                )
        except Exception:
            notification_delivery_total.labels(channel="sms", outcome="failure").inc()
            logger.exception("sms_delivery_failed", extra={"to_number": to_number})
            raise
        notification_delivery_total.labels(channel="sms", outcome="success").inc()


def create_sms_provider() -> SMSProvider:
    settings = get_settings()
    if settings.sms_backend == "twilio":
        return TwilioSMSProvider(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
            api_base_url=settings.twilio_api_base_url,
        )
    return ConsoleSMSProvider()
