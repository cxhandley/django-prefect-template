"""
Configuration for FastAPI gateway - Pydantic v2 compatible.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Prefect
    prefect_api_url: str = "http://localhost:4200/api"
    
    # JWT Authentication
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 10080  # 7 days
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    
    # Redis (for rate limiting)
    redis_url: str = "redis://localhost:6379/0"
    
    # Pydantic v2 uses model_config instead of nested Config class
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    This is cached so settings are only loaded once.
    """
    return Settings()