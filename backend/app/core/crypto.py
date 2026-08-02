"""
Field-level encryption at rest (Phase 9).

Currently used for exactly one column: `users.totp_secret`. A TOTP secret is
the long-term key that generates a user's 2FA codes — if the database were
ever exfiltrated, plaintext TOTP secrets would let an attacker generate
valid codes for every account indefinitely (unlike a password hash, which
at least resists offline cracking). Encrypting it at rest means a raw DB
dump alone isn't enough; the encryption key (which should live in a KMS/
Vault, not the database) is also required.

Uses Fernet (AES-128-CBC + HMAC-SHA256, from the `cryptography` package) —
authenticated symmetric encryption, appropriate for this single-key,
single-tenant-key use case. Not a general-purpose crypto module; add a new
function here deliberately rather than reaching for raw primitives elsewhere
in the codebase.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionNotConfiguredError(Exception):
    """Raised when encrypt/decrypt is attempted without ENCRYPTION_KEY set.

    In production this can never happen — Settings' startup guard refuses to
    boot without it. In development, callers that touch 2FA are expected to
    set ENCRYPTION_KEY too (see .env.example); this exists so the failure
    mode is a clear error instead of a silent no-op or a crash deep in
    `cryptography`."""


def _get_fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise EncryptionNotConfiguredError(
            "ENCRYPTION_KEY is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        # Wrong key, corrupted data, or (most likely in practice) data that
        # was never encrypted in the first place — e.g. a pre-Phase-9 row.
        # Surfaced as a domain-agnostic error; callers decide how to react
        # (auth/service.py treats it as "2FA is unusable, force re-enrollment").
        raise ValueError("Could not decrypt secret — wrong key or corrupted data") from exc
