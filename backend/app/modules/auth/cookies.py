"""
Refresh-token cookie helpers.

The refresh token is set as an HttpOnly, Secure, SameSite=Strict cookie
rather than being returned in the JSON response body — that's the whole
point of this module. A token JavaScript can never read cannot be
exfiltrated by an XSS payload the way a localStorage-held token could be
(see frontend/README.md's now-retired "known tradeoff" section, and
backend/README.md for the full writeup of why this changed).

Scoped to `/api/v1/auth` via `path` — the browser only attaches this cookie
on requests to that prefix (refresh, logout), not on every API call, which
narrows the window in which the token is transmitted at all.
"""
from fastapi import Request, Response

from app.core.config import get_settings

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
_COOKIE_PATH = "/api/v1/auth"


def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=_COOKIE_PATH,
        httponly=True,
        # Secure requires HTTPS in most browsers — except for `localhost`,
        # which every major browser treats as a secure context even over
        # plain HTTP, so this doesn't break local `docker compose up` dev.
        # Tied to is_production rather than hardcoded True purely so a
        # non-localhost, non-HTTPS dev/staging box (an IP-address VM
        # without TLS yet, say) doesn't silently lose the cookie — production
        # itself always terminates TLS at Caddy (see DEPLOYMENT.md).
        secure=settings.is_production,
        samesite="strict",
    )


def clear_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE_NAME, path=_COOKIE_PATH)


def read_refresh_token_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
