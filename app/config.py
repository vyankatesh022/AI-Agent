"""Application configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = Field(
        default="AI Agent API",
        description="Name of the service",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="Semantic version of the application",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: development, staging, or production",
    )
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Cryptographic secret key; must be at least 32 characters long",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Application logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance.

    Avoids re-reading environment variables and .env file on every request.
    """
    return Settings()
