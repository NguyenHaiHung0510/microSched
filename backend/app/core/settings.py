"""Application settings loaded from the environment."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.database_urls import async_postgres_url


class Settings(BaseSettings):
    """Runtime configuration for the application."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The single answer to "where am I running", so no guard ever has to infer it
    # from a neighbouring setting. Two properties are deliberate:
    #
    #   Default is "production" - the only value ever written down is the one that
    #   relaxes a safety rule, and it is written only on a laptop. Forgetting to set
    #   this can therefore never make production lenient.
    #
    #   Literal, not str - `APP_ENV=prod` is a typo that would silently read as "not
    #   production" and disable the guards it gates. Pydantic rejects it at startup
    #   instead, which is the whole point of having one explicit answer.
    app_env: Literal["production", "local"] = "production"

    app_name: str = "microSched"
    app_version: str = "0.1.0"
    git_sha: str = "unknown"
    database_url: str | None = None
    neon_develop_branch_key: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    allowed_emails: str = ""
    oauth_state_secret: str | None = None
    private_pin_bootstrap: str | None = None
    # App-held AES-256 key for the encrypted columns; crypto.py validates and uses it.
    encryption_master_key: str | None = None

    enable_inprocess_cron: bool = False
    vapid_private_key: str | None = None
    vapid_public_key: str | None = None
    vapid_claims_sub: str | None = None

    # auth-brief §2 allows 60-90 days; 90 chosen because the window is rolling, so it
    # only fires after 90 days of zero use. See the 007 PR for the full rationale.
    session_ttl_days: int = 90
    # Only ever false for local http development; production keeps cookies Secure.
    # Left as its own switch on purpose: it answers "how are cookies transported",
    # not "where am I running". Ask `is_production` for the latter.
    session_cookie_secure: bool = True
    # Deliberate escape hatch for the rare case of inspecting the real prod DB
    # from a laptop. Any other local-vs-production host collision refuses boot.
    allow_prod_db_in_local: bool = False
    # Production host references for the fail-closed local guard. The runtime
    # never connects through them; they only define which hosts are prod.
    neon_owner_url: str | None = None
    neon_migrator_url: str | None = None

    @model_validator(mode="after")
    def validate_cron_and_vapid_settings(self) -> "Settings":
        if not self.is_production and self.neon_develop_branch_key:
            self.database_url = async_postgres_url(self.neon_develop_branch_key)
        if self.is_production:
            # Production cookies are always Secure; no env override can weaken this.
            self.session_cookie_secure = True
        elif "session_cookie_secure" not in self.model_fields_set:
            # Unconfigured local runs over plain http, where a Secure cookie is
            # dropped by the browser. An explicit local value is still respected,
            # whether it came from the OS env or from backend/.env.
            self.session_cookie_secure = False
        if not self.is_production and self.database_url:
            # Fail-closed host check: local must never sit on any declared prod
            # host (raw DATABASE_URL env, NEON_OWNER_URL, NEON_MIGRATOR_URL)
            # unless the operator opts in explicitly. The raw env var is read via
            # dotenv (not os.environ) because pydantic does not push .env values
            # into the process environment.
            raw_prod_url = os.environ.get("DATABASE_URL", "")
            current_host = (make_url(self.database_url).host or "").lower()
            env_file = Path(__file__).resolve().parents[1] / ".env"
            if not raw_prod_url and env_file.exists():
                raw_prod_url = dotenv_values(env_file).get("DATABASE_URL") or ""
            declared_hosts = [raw_prod_url, self.neon_owner_url, self.neon_migrator_url]
            prod_hosts = {(make_url(url).host or "").lower() for url in declared_hosts if url}
            if current_host in prod_hosts and not self.allow_prod_db_in_local:
                raise ValueError(
                    "APP_ENV=local refuses to start with the production DATABASE_URL; "
                    "point NEON_DEVELOP_BRANCH_KEY at the develop branch or set "
                    "ALLOW_PROD_DB_IN_LOCAL=true explicitly."
                )
        if self.is_production and self.enable_inprocess_cron:
            if not self.database_url:
                raise ValueError(
                    "database_url is required when enable_inprocess_cron is True in production"
                )
            if not self.vapid_private_key or not self.vapid_public_key or not self.vapid_claims_sub:
                raise ValueError(
                    (
                        "VAPID keys and vapid_claims_sub are required "
                        "when enable_inprocess_cron is True in production"
                    )
                )
        return self

    @property
    def is_production(self) -> bool:
        """Answer the one question every environment-dependent guard should ask."""
        return self.app_env == "production"

    @property
    def allowed_email_set(self) -> frozenset[str]:
        """Return the login allowlist, normalized the same way as Google's claim."""
        return frozenset(
            entry.strip().lower() for entry in self.allowed_emails.split(",") if entry.strip()
        )

    @field_validator("database_url", mode="before")
    @classmethod
    def use_async_postgres_driver(cls, value: object) -> object:
        """Normalize provider-style Postgres URLs for SQLAlchemy async usage."""
        if not isinstance(value, str) or not value:
            return value

        if value.startswith(("postgres://", "postgresql://")):
            return async_postgres_url(value)
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
