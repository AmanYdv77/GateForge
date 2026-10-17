from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration and environment variables schema."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Core Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    PROJECT_NAME: str = "GateForge Gateway"

    # Cryptography & Security
    SECRET_KEY: str = Field(
        default="gateforge-dev-secret-key-minimum-32-characters-required-for-security",
        min_length=32,
        description="Master secret key for application cryptographic signing",
    )
    API_KEY_PREFIX: str = Field(
        default="gfg_live_",
        description="Standardized prefix for production API keys",
    )

    # PostgreSQL Database Settings
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/gateforge",
        description="Asyncpg database connection DSN",
    )
    DB_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DB_TIMEOUT_SECONDS: int = Field(default=30, ge=1)

    # Redis Cache & Sliding Window Settings
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for auth caching and rate limiting",
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=5, le=500)
    AUTH_CACHE_TTL_SECONDS: int = Field(default=300, ge=10, le=86400)

    # Tier-based Rate Limits (Requests per Minute)
    RATE_LIMIT_FREE_RPM: int = Field(default=60, ge=1)
    RATE_LIMIT_PRO_RPM: int = Field(default=600, ge=1)
    RATE_LIMIT_ENTERPRISE_RPM: int = Field(default=6000, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()
