"""
Password hashing (Argon2) and JWT access/refresh token utilities.

Design decisions:
- Argon2id is used for password hashing (memory-hard, OWASP-recommended).
- Refresh tokens are never stored in plaintext — only a SHA-256 hash is persisted.
- Access tokens are short-lived and carry only the claims needed for authorization
  (subject = user id, role, token type) — no sensitive data.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
_password_hasher = PasswordHasher()


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired, or has the wrong type."""


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Any other argon2 error (e.g. malformed hash) is treated as a mismatch,
        # never as an authentication bypass.
        return False


def needs_rehash(password_hash: str) -> bool:
    """Call after a successful login to opportunistically upgrade old hash parameters."""
    return _password_hasher.check_needs_rehash(password_hash)


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------
def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": TokenType.ACCESS.value,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError("Access token is invalid or expired") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise InvalidTokenError("Token is not an access token")
    return dict(payload)


# ---------------------------------------------------------------------------
# Password reset tokens — self-contained JWT, no extra table required.
# A fingerprint of the *current* password hash is embedded so the token is
# automatically invalidated the moment the password changes (implicit
# single-use / no reuse after a successful reset).
# ---------------------------------------------------------------------------
def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_password_reset_token(*, user_id: uuid.UUID, current_password_hash: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "password_reset",
        "pwd_fp": _password_fingerprint(current_password_hash),
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def verify_password_reset_token(token: str, *, current_password_hash: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError("Reset token is invalid or expired") from exc

    if payload.get("type") != "password_reset":
        raise InvalidTokenError("Token is not a password reset token")
    if payload.get("pwd_fp") != _password_fingerprint(current_password_hash):
        raise InvalidTokenError("Reset token has already been used")
    return uuid.UUID(payload["sub"])


# ---------------------------------------------------------------------------
# MFA (TOTP) login challenge tokens — issued when a login's password check
# succeeds but the account has 2FA enabled. Short-lived and single-purpose;
# unlike the refresh token, reuse within the window isn't a meaningful risk
# since presenting it still requires a valid, time-boxed TOTP code.
# ---------------------------------------------------------------------------
def create_mfa_challenge_token(*, user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "mfa_challenge",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def verify_mfa_challenge_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError("MFA challenge token is invalid or expired") from exc

    if payload.get("type") != "mfa_challenge":
        raise InvalidTokenError("Token is not an MFA challenge token")
    return uuid.UUID(payload["sub"])


# ---------------------------------------------------------------------------
# OTP codes for transaction confirmation. Codes are short-lived and
# attempt-limited (see TransferConfirmation), so a fast SHA-256 comparison is
# sufficient here — Argon2 is unnecessary overhead for a 6-digit code that
# expires in minutes and locks out after a handful of wrong attempts.
# ---------------------------------------------------------------------------
def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_otp_code(code: str, code_hash: str) -> bool:
    return secrets.compare_digest(hash_otp_code(code), code_hash)


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) two-factor authentication
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_provisioning_uri(*, secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.project_name)


def verify_totp_code(*, secret: str, code: str) -> bool:
    # valid_window=1 accepts the previous/next 30s step too, tolerating
    # small clock drift between the server and the user's authenticator app.
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------------------------------------------------------------------------
# Refresh tokens — opaque random string, only the hash is ever persisted
# ---------------------------------------------------------------------------
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
