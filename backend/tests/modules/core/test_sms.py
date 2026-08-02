import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from app.core.sms import (
    ConsoleSMSProvider,
    SMSDeliveryError,
    TwilioSMSProvider,
    create_sms_provider,
)


class _MockTwilioHandler(BaseHTTPRequestHandler):
    """
    A tiny real HTTP server that mimics Twilio's Messages resource shape
    closely enough to genuinely exercise TwilioSMSProvider's request
    construction, Basic Auth header, and response parsing — not a mock of
    the Python client, an actual server on a real socket.
    """

    captured_requests: list[dict] = []
    respond_with_error = False

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's naming convention
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        form = {k: v[0] for k, v in parse_qs(raw_body.decode()).items()}

        auth_header = self.headers.get("Authorization", "")
        _MockTwilioHandler.captured_requests.append(
            {"path": self.path, "form": form, "authorization": auth_header}
        )

        if _MockTwilioHandler.respond_with_error:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"code": 21211, "message": "Invalid 'To' Phone Number"}).encode())
            return

        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"sid": "SM_fake_message_sid", "status": "queued"}).encode())

    def log_message(self, format, *args):  # noqa: A002 — silence default stderr logging
        pass


@pytest.fixture
def mock_twilio_server():
    _MockTwilioHandler.captured_requests = []
    _MockTwilioHandler.respond_with_error = False

    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockTwilioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_console_sms_provider_does_not_raise(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.sms")
    provider = ConsoleSMSProvider()
    await provider.send(to_number="+994501234567", body="Your code is 123456")
    assert any("sms_dispatched_console_backend" in r.getMessage() for r in caplog.records)
    # The message body (which may contain an OTP) must never be logged.
    assert not any("123456" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_twilio_sms_provider_sends_correct_request_to_real_local_server(mock_twilio_server):
    provider = TwilioSMSProvider(
        account_sid="AC_test_sid",
        auth_token="test_auth_token",
        from_number="+15005550006",
        api_base_url=mock_twilio_server,
    )

    await provider.send(to_number="+994501234567", body="Your code is 654321")

    assert len(_MockTwilioHandler.captured_requests) == 1
    request = _MockTwilioHandler.captured_requests[0]
    assert request["path"] == "/2010-04-01/Accounts/AC_test_sid/Messages.json"
    assert request["form"]["To"] == "+994501234567"
    assert request["form"]["From"] == "+15005550006"
    assert request["form"]["Body"] == "Your code is 654321"

    expected_auth = "Basic " + base64.b64encode(b"AC_test_sid:test_auth_token").decode()
    assert request["authorization"] == expected_auth


@pytest.mark.asyncio
async def test_twilio_sms_provider_raises_on_error_response(mock_twilio_server):
    _MockTwilioHandler.respond_with_error = True
    provider = TwilioSMSProvider(
        account_sid="AC_test_sid",
        auth_token="test_auth_token",
        from_number="+15005550006",
        api_base_url=mock_twilio_server,
    )

    with pytest.raises(SMSDeliveryError, match="Invalid 'To' Phone Number"):
        await provider.send(to_number="not-a-number", body="test")


def test_create_sms_provider_returns_console_by_default(monkeypatch):
    monkeypatch.setenv("SMS_BACKEND", "console")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert isinstance(create_sms_provider(), ConsoleSMSProvider)
    finally:
        get_settings.cache_clear()


def test_create_sms_provider_returns_twilio_when_configured(monkeypatch):
    monkeypatch.setenv("SMS_BACKEND", "twilio")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert isinstance(create_sms_provider(), TwilioSMSProvider)
    finally:
        monkeypatch.delenv("SMS_BACKEND", raising=False)
        get_settings.cache_clear()
