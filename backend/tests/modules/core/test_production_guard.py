"""
Tests for the production configuration guard (app/core/config.py).

These construct `Settings` directly with monkeypatched env vars rather than
going through the `client`/`app` fixtures, since the whole point is to
verify Settings() itself raises — by the time an app/client fixture exists,
settings have already been validated successfully.
"""
import pytest
from cryptography.fernet import Fernet


def _clear_settings_cache():
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache_after_test():
    yield
    _clear_settings_cache()


def _base_production_env(monkeypatch, **overrides):
    env = {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "a" * 40,
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        **overrides,
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_production_refuses_default_jwt_secret(monkeypatch):
    _base_production_env(monkeypatch, JWT_SECRET_KEY="change_me_super_secret")
    from app.core.config import Settings

    with pytest.raises(ValueError, match="JWT_SECRET_KEY is still the default"):
        Settings()


def test_production_refuses_short_jwt_secret(monkeypatch):
    _base_production_env(monkeypatch, JWT_SECRET_KEY="tooshort")
    from app.core.config import Settings

    with pytest.raises(ValueError, match="at least 32"):
        Settings()


def test_production_refuses_cors_wildcard(monkeypatch):
    _base_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["*"]')
    from app.core.config import Settings

    with pytest.raises(ValueError, match="wildcard"):
        Settings()


def test_production_accepts_explicit_origin_list(monkeypatch):
    _base_production_env(monkeypatch)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://bank.example.com"]')
    from app.core.config import Settings

    settings = Settings()
    assert settings.cors_allow_origins == ["https://bank.example.com"]


def test_production_refuses_missing_encryption_key(monkeypatch):
    _base_production_env(monkeypatch, ENCRYPTION_KEY="")
    from app.core.config import Settings

    with pytest.raises(ValueError, match="ENCRYPTION_KEY is not set"):
        Settings()


def test_production_refuses_malformed_encryption_key(monkeypatch):
    _base_production_env(monkeypatch, ENCRYPTION_KEY="not-a-real-fernet-key")
    from app.core.config import Settings

    with pytest.raises(ValueError, match="not a valid Fernet key"):
        Settings()


def test_production_accepts_fully_valid_configuration(monkeypatch):
    _base_production_env(monkeypatch)
    from app.core.config import Settings

    settings = Settings()
    assert settings.is_production is True


def test_development_ignores_all_production_guards(monkeypatch):
    """The whole point of the guard is that it's production-only — every
    one of the above violations must be fine outside production, since
    that's exactly the default local-dev configuration."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "change_me_super_secret")
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["*"]')
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    from app.core.config import Settings

    settings = Settings()
    assert settings.is_production is False


def test_multiple_violations_are_all_reported_together(monkeypatch):
    """A single failed deploy attempt should show every problem at once,
    not make the operator fix-and-redeploy one error at a time."""
    _base_production_env(
        monkeypatch, JWT_SECRET_KEY="change_me_super_secret", ENCRYPTION_KEY=""
    )
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["*"]')
    from app.core.config import Settings

    with pytest.raises(ValueError) as exc_info:
        Settings()
    message = str(exc_info.value)
    assert "JWT_SECRET_KEY is still the default" in message
    assert "wildcard" in message
    assert "ENCRYPTION_KEY is not set" in message
