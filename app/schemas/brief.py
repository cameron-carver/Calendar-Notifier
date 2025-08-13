from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class AttendeeInfo(BaseModel):
    """Information about a meeting attendee."""
    email: str
    name: str
    company: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    recent_emails: Optional[List[str]] = None
    # Affinity enrichment
    last_note_summary: Optional[str] = None
    last_note_date: Optional[str] = None
    materials: Optional[List[str]] = None
    company_domain: Optional[str] = None
    website_url: Optional[str] = None
    news_articles: Optional[List[Dict[str, Any]]] = None
    # Relationship history
    last_meeting_date: Optional[datetime] = None
    meetings_past_n_days: Optional[int] = None


class MeetingEvent(BaseModel):
    """Meeting event information."""
    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: List[AttendeeInfo]
    description: Optional[str] = None
    location: Optional[str] = None
    # Quick access
    meeting_url: Optional[str] = None
    calendar_url: Optional[str] = None
    duration_minutes: Optional[int] = None


class BriefRequest(BaseModel):
    """Request to generate a brief."""
    date: Optional[datetime] = None
    force_regenerate: bool = False


class BriefResponse(BaseModel):
    """Response containing the generated brief."""
    id: int
    date: datetime
    content: str
    events_summary: List[MeetingEvent]
    created_at: datetime
    is_sent: bool


class UserSettingsRequest(BaseModel):
    """Request to update user settings."""
    delivery_time: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = "America/New_York"
    email_address: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    is_active: bool = True


class UserSettingsResponse(BaseModel):
    """Response containing user settings."""
    id: int
    delivery_time: str
    timezone: str
    email_address: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None 