"""Application settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    google_client_id: str | None = None
    google_client_secret: str | None = None
    allowed_emails: str = ""
    oauth_state_secret: str | None = None
    cron_token: str | None = None

    # auth-brief §2 allows 60-90 days; 90 chosen because the window is rolling, so it
    # only fires after 90 days of zero use. See the 007 PR for the full rationale.
    session_ttl_days: int = 90
    # Only ever false for local http development; production keeps cookies Secure.
    # Left as its own switch on purpose: it answers "how are cookies transported",
    # not "where am I running". Ask `is_production` for the latter.
    session_cookie_secure: bool = True

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
