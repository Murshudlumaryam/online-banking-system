import asyncio

import pytest

from app.core.email import (
    ConsoleEmailProvider,
    SMTPEmailProvider,
    create_email_provider,
)


@pytest.mark.asyncio
async def test_console_email_provider_does_not_raise(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.email")
    provider = ConsoleEmailProvider()
    await provider.send(to_address="customer@example.com", subject="Hello", body="Test body")
    assert any("email_dispatched_console_backend" in record.getMessage() for record in caplog.records)


def test_create_email_provider_returns_console_by_default(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = create_email_provider()
        assert isinstance(provider, ConsoleEmailProvider)
    finally:
        get_settings.cache_clear()


def test_create_email_provider_returns_smtp_when_configured(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = create_email_provider()
        assert isinstance(provider, SMTPEmailProvider)
    finally:
        monkeypatch.delenv("EMAIL_BACKEND", raising=False)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_smtp_email_provider_actually_delivers_to_a_real_local_server():
    """
    Spins up a real (non-mocked) local SMTP debug server via aiosmtpd and
    verifies SMTPEmailProvider genuinely delivers a message to it — not just
    that it calls a mocked function without raising.
    """
    from aiosmtpd.controller import Controller

    received: list[dict] = []

    class _CapturingHandler:
        async def handle_DATA(self, server, session, envelope):
            received.append(
                {
                    "mail_from": envelope.mail_from,
                    "rcpt_tos": list(envelope.rcpt_tos),
                    "content": envelope.content.decode("utf-8", errors="replace"),
                }
            )
            return "250 Message accepted for delivery"

    # aiosmtpd's Controller doesn't reliably support port=0 ("let the OS
    # choose") — it tries to verify startup by reconnecting to the literal
    # port value before the OS-assigned port is known. Pick a genuinely free
    # port ourselves instead.
    import socket as socket_module

    with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    controller = Controller(_CapturingHandler(), hostname="127.0.0.1", port=free_port)
    controller.start()
    try:
        provider = SMTPEmailProvider(
            host="127.0.0.1",
            port=free_port,
            username="",
            password="",
            use_tls=False,
            from_address="no-reply@example-bank.internal",
        )
        await provider.send(
            to_address="customer@example.com",
            subject="Your transfer confirmation code",
            body="Your one-time code is: 123456",
        )

        # Give the asyncio event loop inside aiosmtpd's controller thread a
        # moment to process the already-completed SMTP transaction.
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.05)
    finally:
        controller.stop()

    assert len(received) == 1
    assert received[0]["mail_from"] == "no-reply@example-bank.internal"
    assert received[0]["rcpt_tos"] == ["customer@example.com"]
    assert "Your transfer confirmation code" in received[0]["content"]
    assert "123456" in received[0]["content"]
