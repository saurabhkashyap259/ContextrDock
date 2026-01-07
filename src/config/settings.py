"""Configuration settings for ContextDock application.

Loads environment variables using Pydantic Settings and provides
typed configuration access throughout the application.
"""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://contextdock:password@localhost:5432/contextdock",
        description="PostgreSQL connection string",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string",
    )

    # Qdrant Vector Database
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant vector database URL",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key (optional for local instances)",
    )

    # LLM Provider API Keys
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for embeddings and LLM",
    )
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key for Claude models",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama base URL for local LLM",
    )

    # Security
    secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT token signing (min 32 chars)",
    )
    fernet_key: str = Field(
        ...,
        description="Fernet key for encrypting connector credentials",
    )

    # JWT Configuration
    jwt_access_token_expire_minutes: int = Field(
        default=15,
        description="JWT access token expiration in minutes",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="JWT refresh token expiration in days",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL",
    )

    # Slack Bot (optional)
    slack_bot_token: str | None = Field(
        default=None,
        description="Slack bot token for Slack integration",
    )
    slack_signing_secret: str | None = Field(
        default=None,
        description="Slack signing secret for request verification",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure secret key meets minimum length requirement."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env == "development"


# Global settings instance
settings = Settings()
