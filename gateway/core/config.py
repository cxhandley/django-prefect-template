"""
Configuration for FastAPI gateway.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    prefect_api_url: str = "http://localhost:4200/api"
    jwt_secret: str = "change-me-in-production"
    
    class Config:
        env_prefix = "GATEWAY_"
        case_sensitive = False


settings = Settings()