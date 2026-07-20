"""Application settings loaded from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the application."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "microSched"
    app_version: str = "0.1.0"
    database_url: str | None = None
