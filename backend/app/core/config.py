"""
Central application configuration.

All configuration is loaded from environment variables (see .env.example).
Never hardcode secrets here — this module only defines the shape and defaults
for local development.
"""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change_me_super_secret"
_MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General ---
    environment: str = Field(default="development")
    api_v1_prefix: str = Field(default="/api/v1")
    project_name: str = Field(default="Online Banking System")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://banking_user:banking_pass@db:5432/banking_db"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_echo: bool = Field(default=False)

    # --- Redis / Celery ---
    redis_url: str = Field(default="redis://redis:6379/0")

    # --- JWT / security ---
    jwt_secret_key: str = Field(default=_DEFAULT_JWT_SECRET)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)
    otp_expire_minutes: int = Field(default=5)
    otp_max_attempts: int = Field(default=5)

    # --- Field-level encryption at rest (Phase 9) ---
    # Encrypts sensitive columns (currently: users.totp_secret) before they
    # ever reach the database. Must be a valid Fernet key — generate one
    # with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # See app/core/crypto.py and app/core/secrets_provider.py for how this
    # is meant to be swapped for a real KMS/Vault-backed key in production.
    encryption_key: str = Field(default="")

    # --- Rate limiting ---
    # Format: (limit, window_seconds). Auth endpoints get tighter limits than
    # general API traffic; password-reset-request is separately throttled
    # (tighter) since it triggers an outbound notification per call.
    rate_limit_login_per_minute: int = Field(default=10)
    rate_limit_register_per_minute: int = Field(default=5)
    rate_limit_password_reset_per_minute: int = Field(default=3)
    rate_limit_transfer_per_minute: int = Field(default=20)
    rate_limit_default_per_minute: int = Field(default=120)
    rate_limit_backend: str = Field(default="redis")  # "redis" or "memory" (tests/local dev)

    # --- Email (Phase 7) ---
    email_backend: str = Field(default="console")  # "console" (logs only) or "smtp" (real send)
    # Which channel(s) carry the transfer-confirmation OTP. Previously
    # hardcoded to "sms" in TransactionService.initiate_transfer, which
    # meant it could never reach an inbox at all unless Twilio credentials
    # were configured — a real Gmail address configured via SMTP had no
    # delivery path whatsoever. "email" is the default because it's the
    # channel every environment (including a bare `cp .env.example .env`
    # dev setup) can actually exercise end-to-end without a paid SMS
    # provider. "sms" and "both" remain available for deployments that do
    # have Twilio configured.
    otp_delivery_channel: str = Field(default="email")  # "email" | "sms" | "both"
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)
    smtp_from_address: str = Field(default="no-reply@example-bank.internal")

    # --- SMS (Phase 8) ---
    sms_backend: str = Field(default="console")  # "console" (logs only) or "twilio" (real send)
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_from_number: str = Field(default="")
    # Overridable so tests can point the client at a local mock server
    # instead of the real Twilio API.
    twilio_api_base_url: str = Field(default="https://api.twilio.com")

    # --- CORS ---
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    # Whether to trust X-Forwarded-For for the client IP recorded in audit
    # logs (login/register/refresh/MFA events). Defaults to False — a
    # request handled directly (no reverse proxy in front) can set this
    # header to anything, and honoring it unconditionally lets an attacker
    # poison the audit trail with a fake IP. Only enable this when the app
    # is deployed behind a reverse proxy that is known to strip/overwrite
    # any client-supplied X-Forwarded-For before setting its own (this
    # project's Caddyfile does, for the production deployment path) — see
    # app.modules.auth.dependencies.get_client_ip.
    trust_proxy_headers: bool = Field(default=False)

    # --- Observability (Phase 9) ---
    metrics_enabled: bool = Field(default=True)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _guard_production_configuration(self) -> "Settings":
        """
        Fails app startup immediately (rather than serving traffic insecurely)
        if the process is configured as `ENVIRONMENT=production` but still
        carries dev-only defaults. This is deliberately a hard error, not a
        warning — a misconfigured production deploy should refuse to boot,
        not boot weakly. Every check here is something DEPLOYMENT.md tells
        an operator to set explicitly.
        """
        if not self.is_production:
            return self

        errors: list[str] = []

        if self.jwt_secret_key == _DEFAULT_JWT_SECRET:
            errors.append(
                "JWT_SECRET_KEY is still the default value — set a real secret "
                "(e.g. `openssl rand -base64 32`)."
            )
        if len(self.jwt_secret_key) < _MIN_PRODUCTION_SECRET_LENGTH:
            errors.append(
                f"JWT_SECRET_KEY must be at least {_MIN_PRODUCTION_SECRET_LENGTH} "
                f"characters in production (got {len(self.jwt_secret_key)})."
            )

        if "*" in self.cors_allow_origins:
            errors.append(
                "CORS_ALLOW_ORIGINS contains a wildcard ('*') — combined with "
                "allow_credentials=True this allows any site to make "
                "authenticated requests on a signed-in user's behalf. List "
                "your real frontend origin(s) explicitly instead."
            )

        if not self.encryption_key:
            errors.append(
                "ENCRYPTION_KEY is not set — required in production to encrypt "
                "2FA secrets at rest. Generate one with: python -c \"from "
                "cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        else:
            try:
                from cryptography.fernet import Fernet

                Fernet(self.encryption_key.encode())
            except Exception:
                errors.append(
                    "ENCRYPTION_KEY is set but is not a valid Fernet key. Generate one "
                    'with: python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"'
                )

        if errors:
            joined = "\n  - ".join(errors)
            raise ValueError(f"Refusing to start with an insecure production configuration:\n  - {joined}")

        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import and call this, never instantiate Settings() directly."""
    return Settings()
