from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    google_calendar_credentials_file: str
    # Comma-separated list of Google Calendar IDs (e.g., emails or calendar IDs). If empty, uses 'primary'
    google_calendar_ids: Optional[str] = None
    affinity_api_key: str
    openai_api_key: str
    news_api_key: Optional[str] = None
    gmail_credentials_file: str
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # App Settings
    default_delivery_time: str = "08:00"
    timezone: str = "America/New_York"
    environment: str = "development"
    
    # Optional settings
    max_news_articles_per_person: int = 3
    brief_summary_length: int = 500

    # Filters
    filter_require_non_owner_attendee: bool = True
    filter_external_only: bool = True
    filter_exclude_recurring: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 