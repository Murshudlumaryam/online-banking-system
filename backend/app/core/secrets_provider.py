"""
Secrets provider abstraction (Phase 9).

Today, every secret (JWT_SECRET_KEY, ENCRYPTION_KEY, POSTGRES_PASSWORD,
SMTP/TWILIO credentials) comes from environment variables via
`app.core.config.Settings` — which is exactly right for a single-VM
deployment with a `.env` file (see DEPLOYMENT.md), and is genuinely fine at
that scale: the `.env` file is 600-permissioned, never committed, and
rotated by hand.

Once secrets need to be shared across multiple hosts, rotated automatically,
or audited (who read which secret, when), that model stops being enough —
that's what HashiCorp Vault / AWS Secrets Manager / GCP Secret Manager are
for. This module defines the seam to swap in one of those *without* the
Settings model or any call site changing: implement `SecretsProvider`,
point `create_secrets_provider()` at it, and every secret read still goes
through `get_settings()` as before — the provider just becomes what
populates the environment before Settings reads it.

This module intentionally does NOT include a real Vault/AWS SDK client —
this sandbox has no network path to either, so anything written here would
be structurally-plausible but functionally unverified. What's here (the
Protocol, the env-based default, and the concrete integration recipes below)
is real and complete; wiring in `hvac` (Vault) or `boto3` (AWS) is a
same-shaped, mechanical follow-up once real credentials exist to test
against.
"""
from typing import Protocol


class SecretsProvider(Protocol):
    def get_secret(self, key: str) -> str | None: ...


class EnvSecretsProvider:
    """The current, default provider — reads from the process environment
    (which for local/single-VM deployments is populated by `.env` via
    docker-compose's `env_file:` directive). This is what
    `app.core.config.Settings` uses implicitly via pydantic-settings."""

    def get_secret(self, key: str) -> str | None:
        import os

        return os.environ.get(key)


# ---------------------------------------------------------------------------
# Integration recipes for a real secrets backend (not wired in — see module
# docstring). Each would be a few dozen lines implementing SecretsProvider:
#
# HashiCorp Vault (via the `hvac` package):
#   class VaultSecretsProvider:
#       def __init__(self, vault_addr: str, vault_token: str, mount_path: str):
#           import hvac
#           self._client = hvac.Client(url=vault_addr, token=vault_token)
#           self._mount_path = mount_path
#       def get_secret(self, key: str) -> str | None:
#           resp = self._client.secrets.kv.v2.read_secret_version(
#               path=key, mount_point=self._mount_path
#           )
#           return resp["data"]["data"].get("value")
#
# AWS Secrets Manager (via `boto3`):
#   class AWSSecretsManagerProvider:
#       def __init__(self, region_name: str):
#           import boto3
#           self._client = boto3.client("secretsmanager", region_name=region_name)
#       def get_secret(self, key: str) -> str | None:
#           try:
#               resp = self._client.get_secret_value(SecretId=key)
#               return resp.get("SecretString")
#           except self._client.exceptions.ResourceNotFoundException:
#               return None
#
# GCP Secret Manager (via `google-cloud-secret-manager`):
#   class GCPSecretManagerProvider:
#       def __init__(self, project_id: str):
#           from google.cloud import secretmanager
#           self._client = secretmanager.SecretManagerServiceClient()
#           self._project_id = project_id
#       def get_secret(self, key: str) -> str | None:
#           name = f"projects/{self._project_id}/secrets/{key}/versions/latest"
#           resp = self._client.access_secret_version(name=name)
#           return resp.payload.data.decode("utf-8")
#
# In every case, the typical rollout is: fetch secrets from the provider at
# container startup (an entrypoint script, before uvicorn/gunicorn starts),
# export them as environment variables, and Settings picks them up exactly
# as it does today — no application code changes needed beyond that
# entrypoint. Rotation still requires a restart unless you also add a
# periodic re-fetch + `get_settings.cache_clear()`, which is a reasonable
# next step once this is actually load-bearing.
# ---------------------------------------------------------------------------


def create_secrets_provider() -> SecretsProvider:
    return EnvSecretsProvider()
