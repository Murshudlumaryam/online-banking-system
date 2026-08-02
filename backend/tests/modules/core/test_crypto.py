import pytest
from cryptography.fernet import Fernet

from app.core.crypto import EncryptionNotConfiguredError, decrypt_secret, encrypt_secret


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    from app.core.config import get_settings

    yield
    get_settings.cache_clear()


def test_encrypt_then_decrypt_round_trips():
    plaintext = "JBSWY3DPEHPK3PXP"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert decrypt_secret(ciphertext) == plaintext


def test_ciphertext_is_not_plaintext_and_looks_like_a_fernet_token():
    plaintext = "JBSWY3DPEHPK3PXP"
    ciphertext = encrypt_secret(plaintext)
    assert plaintext not in ciphertext
    # Fernet tokens are urlsafe-base64; a real one round-trips through Fernet directly too.
    from app.core.config import get_settings

    Fernet(get_settings().encryption_key.encode()).decrypt(ciphertext.encode())


def test_decrypting_garbage_raises_value_error():
    with pytest.raises(ValueError, match="wrong key or corrupted data"):
        decrypt_secret("not-a-real-encrypted-token")


def test_decrypting_with_a_different_key_fails(monkeypatch):
    plaintext = "JBSWY3DPEHPK3PXP"
    ciphertext = encrypt_secret(plaintext)

    from app.core.config import get_settings

    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="wrong key or corrupted data"):
        decrypt_secret(ciphertext)


def test_encrypt_raises_clear_error_when_key_not_configured(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ENCRYPTION_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(EncryptionNotConfiguredError):
        encrypt_secret("some-secret")
