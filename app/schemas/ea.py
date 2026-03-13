"""
Pydantic schemas for EA mode API endpoints.

Provides request/response models for executives, annotations, and relationships
with full validation.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re
from app.schemas.enums import Priority, RelationshipStrength, RelationshipStatus


# ============================================================================
# EXECUTIVE SCHEMAS
# ============================================================================

class ExecutiveBase(BaseModel):
    """Base schema for executive data."""
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    title: Optional[str] = Field(None, max_length=255)
    google_calendar_ids: List[str] = Field(min_length=1)
    timezone: str = "America/New_York"
    delivery_time: str = Field(default="08:00", pattern=r'^\d{2}:\d{2}$')

    @validator('google_calendar_ids')
    def validate_calendar_ids(cls, v):
        """Ensure at least one calendar ID is provided."""
        if not v or len(v) == 0:
            raise ValueError("At least one calendar ID required")
        return v


class ExecutiveCreate(ExecutiveBase):
    """Schema for creating a new executive."""
    pass


class ExecutiveUpdate(BaseModel):
    """Schema for updating executive profile (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    title: Optional[str] = None
    google_calendar_ids: Optional[List[str]] = None
    delivery_time: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}$')
    delivery_schedule: Optional[Dict[str, str]] = None
    timezone: Optional[str] = None
    email_recipient: Optional[str] = None
    content_depth: Optional[str] = None
    time_window_hours: Optional[int] = None
    enable_ai_prep: Optional[bool] = None
    enable_news: Optional[bool] = None
    enable_meeting_history: Optional[bool] = None
    enable_affinity_data: Optional[bool] = None
    enable_web_enrichment: Optional[bool] = None
    filter_require_non_owner: Optional[bool] = None
    filter_external_only: Optional[bool] = None
    filter_exclude_recurring: Optional[bool] = None
    focus_area: Optional[str] = None
    linkedin_url: Optional[str] = None
    internal_domains: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @validator('delivery_schedule')
    def validate_schedule(cls, v):
        """Validate delivery schedule format."""
        if v:
            valid_days = {'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'default'}
            for day, time in v.items():
                if day.lower() not in valid_days:
                    raise ValueError(f"Invalid day: {day}")
                if not re.match(r'^\d{2}:\d{2}$', time):
                    raise ValueError(f"Invalid time format: {time}")
        return v


class ExecutiveResponse(ExecutiveBase):
    """Schema for executive response."""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# ANNOTATION SCHEMAS
# ============================================================================

class AnnotationCreate(BaseModel):
    """Schema for creating a meeting annotation."""
    event_id: str = Field(min_length=1)
    priority: Priority = Priority.NORMAL
    prep_notes: Optional[str] = None
    action_before_meeting: Optional[str] = None


class AnnotationUpdate(BaseModel):
    """Schema for updating annotation (all fields optional)."""
    priority: Optional[Priority] = None
    prep_notes: Optional[str] = None
    action_before_meeting: Optional[str] = None
    post_meeting_notes: Optional[str] = None
    decisions_made: Optional[str] = None
    action_items: Optional[List[Dict[str, str]]] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = None


class AnnotationResponse(BaseModel):
    """Schema for annotation response."""
    id: int
    executive_id: int
    event_id: str
    priority: str
    prep_notes: Optional[str]
    action_before_meeting: Optional[str]
    post_meeting_notes: Optional[str]
    decisions_made: Optional[str]
    action_items: Optional[List[Dict[str, str]]]
    follow_up_required: bool
    follow_up_date: Optional[datetime]
    follow_up_notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# RELATIONSHIP SCHEMAS
# ============================================================================

class RelationshipCreate(BaseModel):
    """Schema for creating a relationship record."""
    person_email: str = Field(pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    person_name: Optional[str] = Field(None, max_length=255)
    person_company: Optional[str] = Field(None, max_length=255)
    relationship_strength: RelationshipStrength = RelationshipStrength.NEW
    relationship_status: Optional[RelationshipStatus] = None
    relationship_notes: Optional[str] = None


class RelationshipUpdate(BaseModel):
    """Schema for updating relationship (all fields optional)."""
    person_name: Optional[str] = None
    person_company: Optional[str] = None
    relationship_strength: Optional[RelationshipStrength] = None
    relationship_status: Optional[RelationshipStatus] = None
    relationship_notes: Optional[str] = None
    personal_details: Optional[Dict[str, Any]] = None
    linkedin_url: Optional[str] = None
    follow_up_cadence_days: Optional[int] = None


class RelationshipResponse(BaseModel):
    """Schema for relationship response."""
    id: int
    executive_id: int
    person_email: str
    person_name: Optional[str]
    person_company: Optional[str]
    relationship_strength: str
    relationship_status: Optional[str]
    relationship_notes: Optional[str]
    personal_details: Optional[Dict[str, Any]]
    linkedin_url: Optional[str]
    first_met_date: Optional[datetime]
    last_met_date: Optional[datetime]
    total_meetings: int
    last_follow_up: Optional[datetime]
    next_follow_up: Optional[datetime]
    follow_up_cadence_days: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
