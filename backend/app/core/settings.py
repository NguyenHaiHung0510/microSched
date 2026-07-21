"""Application settings loaded from the environment."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_urls import async_postgres_url


class Settings(BaseSettings):
    """Runtime configuration for the application."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "microSched"
    app_version: str = "0.1.0"
    database_url: str | None = None

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
