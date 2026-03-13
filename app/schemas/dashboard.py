"""
Pydantic schemas for dashboard API endpoints.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List, Any
from datetime import datetime


class DashboardSettingsRequest(BaseModel):
    """Request schema for updating user dashboard settings."""

    delivery_schedule: Optional[Dict[str, str]] = Field(
        None,
        description="Day-specific delivery times. Keys: monday-sunday, default. Values: HH:MM format"
    )
    content_depth: Optional[str] = Field(
        "standard",
        description="Content depth: quick, standard, or detailed"
    )
    time_window_hours: Optional[int] = Field(
        None,
        description="Meeting window in hours (0 = all day)",
        ge=0,
        le=24
    )

    # Feature toggles
    enable_ai_prep: Optional[bool] = Field(None, description="Enable AI meeting prep generation")
    enable_news: Optional[bool] = Field(None, description="Enable news article enrichment")
    enable_meeting_history: Optional[bool] = Field(None, description="Enable meeting history tracking")
    enable_affinity_data: Optional[bool] = Field(None, description="Enable Affinity CRM data")
    enable_web_enrichment: Optional[bool] = Field(None, description="Enable web enrichment fallback")

    # Filter preferences
    filter_require_non_owner: Optional[bool] = Field(None, description="Require non-owner attendees")
    filter_external_only: Optional[bool] = Field(None, description="Only external meetings")
    filter_exclude_recurring: Optional[bool] = Field(None, description="Exclude recurring meetings")

    # Content limits
    max_news_articles: Optional[int] = Field(None, description="Max news articles per person", ge=0, le=10)
    talking_points_enabled: Optional[bool] = Field(None, description="Enable talking points")

    @validator("content_depth")
    def validate_content_depth(cls, v):
        """Validate content depth is one of the allowed values."""
        if v not in ["quick", "standard", "detailed"]:
            raise ValueError("content_depth must be one of: quick, standard, detailed")
        return v

    @validator("delivery_schedule")
    def validate_delivery_schedule(cls, v):
        """Validate delivery schedule format."""
        if v is None:
            return v

        valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "default"}
        for day, time in v.items():
            if day not in valid_days:
                raise ValueError(f"Invalid day: {day}. Must be one of: {valid_days}")
            # Validate time format (HH:MM)
            try:
                hours, minutes = time.split(":")
                h, m = int(hours), int(minutes)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError(f"Invalid time: {time}. Hours must be 0-23, minutes 0-59")
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid time format: {time}. Expected HH:MM")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "delivery_schedule": {
                    "monday": "07:00",
                    "tuesday": "07:30",
                    "default": "08:00"
                },
                "content_depth": "standard",
                "time_window_hours": 4,
                "enable_ai_prep": True,
                "enable_news": True
            }
        }


class DashboardSettingsResponse(BaseModel):
    """Response schema for user dashboard settings."""

    id: int
    email_address: str
    is_active: bool
    timezone: str

    # Delivery settings
    delivery_time: str
    delivery_schedule: Optional[Dict[str, str]]

    # Content preferences
    content_depth: str
    time_window_hours: Optional[int]

    # Feature toggles
    enable_ai_prep: Optional[bool]
    enable_news: Optional[bool]
    enable_meeting_history: Optional[bool]
    enable_affinity_data: Optional[bool]
    enable_web_enrichment: Optional[bool]

    # Filter preferences
    filter_require_non_owner: Optional[bool]
    filter_external_only: Optional[bool]
    filter_exclude_recurring: Optional[bool]

    # Content limits
    max_news_articles: Optional[int]
    talking_points_enabled: Optional[bool]

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class FilterPresetRequest(BaseModel):
    """Request schema for creating/updating filter presets."""

    name: str = Field(..., min_length=1, max_length=100, description="Preset name")
    description: Optional[str] = Field(None, max_length=255, description="Preset description")
    filters: Dict[str, Any] = Field(..., description="Filter configuration as JSON")

    @validator("filters")
    def validate_filters(cls, v):
        """Validate filter configuration structure."""
        valid_keys = {
            "require_non_owner",
            "external_only",
            "exclude_recurring",
            "persona_types",
            "time_window_hours",
            "relationship_signal"
        }

        for key in v.keys():
            if key not in valid_keys:
                raise ValueError(f"Invalid filter key: {key}. Valid keys: {valid_keys}")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Founders Only",
                "description": "Only show meetings with portfolio founders",
                "filters": {
                    "persona_types": ["founder"],
                    "external_only": True,
                    "time_window_hours": 4
                }
            }
        }


class FilterPresetResponse(BaseModel):
    """Response schema for filter presets."""

    id: int
    user_id: int
    name: str
    description: Optional[str]
    filters: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MetricsResponse(BaseModel):
    """Response schema for aggregated usage metrics."""

    # Aggregated statistics
    total_briefs: int = Field(description="Total briefs generated in period")
    total_meetings: int = Field(description="Total meetings processed")
    total_tokens: int = Field(description="Total OpenAI tokens used")
    avg_generation_time: float = Field(description="Average generation time in seconds")
    enrichment_rate: float = Field(description="Percentage of meetings successfully enriched")

    # Detailed breakdowns
    meetings_with_ai_prep: int = Field(description="Meetings with AI prep generated")
    affinity_api_calls: int = Field(description="Total Affinity API calls")
    news_api_calls: int = Field(description="Total News API calls")
    linkedin_found: int = Field(description="LinkedIn profiles found")
    news_articles_found: int = Field(description="News articles found")
    company_data_found: int = Field(description="Company descriptions found")

    # Time period
    days_analyzed: int = Field(description="Number of days in analysis period")

    class Config:
        json_schema_extra = {
            "example": {
                "total_briefs": 30,
                "total_meetings": 150,
                "total_tokens": 45000,
                "avg_generation_time": 12.5,
                "enrichment_rate": 0.87,
                "meetings_with_ai_prep": 120,
                "affinity_api_calls": 450,
                "news_api_calls": 300,
                "linkedin_found": 130,
                "news_articles_found": 240,
                "company_data_found": 140,
                "days_analyzed": 30
            }
        }


class BriefPreviewRequest(BaseModel):
    """Request schema for generating brief preview."""

    date: Optional[str] = Field(
        None,
        description="Date for preview (YYYY-MM-DD). Defaults to today."
    )
    custom_settings: Optional[Dict[str, Any]] = Field(
        None,
        description="Temporary settings overrides for preview"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-02-11",
                "custom_settings": {
                    "content_depth": "quick",
                    "enable_news": False,
                    "time_window_hours": 4
                }
            }
        }
