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
    company_description: Optional[str] = None
    news_articles: Optional[List[Dict[str, Any]]] = None
    # Affinity pipeline
    affinity_list_name: Optional[str] = None
    affinity_stage: Optional[str] = None
    # Persona classification
    persona_type: Optional[str] = None
    # Relationship history
    last_meeting_date: Optional[datetime] = None
    meetings_past_n_days: Optional[int] = None
    recent_meeting_titles: Optional[List[str]] = None
    # EA mode: Relationship context
    relationship_strength: Optional[str] = None
    relationship_notes: Optional[str] = None
    personal_details: Optional[Dict[str, Any]] = None
    # Network Builder graph metrics
    network_pagerank: Optional[float] = None
    network_centrality: Optional[float] = None
    network_cluster_id: Optional[int] = None
    network_total_connections: Optional[int] = None
    network_strength_label: Optional[str] = None
    network_decay_score: Optional[float] = None
    connection_path: Optional[List[str]] = None


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
    # Recurring event flag (lightweight rendering, skip enrichment)
    is_recurring: bool = False
    # AI-generated prep (per-meeting)
    ai_summary: Optional[Dict[str, Any]] = None
    # EA mode: Annotation context
    annotation: Optional[Dict[str, Any]] = None


class NewsArticle(BaseModel):
    """AI/tech news article from web search."""
    title: str
    url: Optional[str] = None
    source: Optional[str] = None          # e.g. "Hacker News", "TechCrunch"
    summary: Optional[str] = None         # 1-2 sentence summary
    relevance_tag: Optional[str] = None   # e.g. "deployment", "research", "tooling"


class TodoItem(BaseModel):
    """Actionable item from journal or DB."""
    description: str
    source: str                           # "journal", "follow-up", "action-item"
    priority: Optional[str] = None        # "high", "normal", "low"
    due_date: Optional[datetime] = None
    person_name: Optional[str] = None
    person_company: Optional[str] = None
    completed: bool = False


class TimeBlock(BaseModel):
    """AI-suggested time block for the day."""
    title: str                            # e.g. "Deep dive: LLM inference optimization"
    description: str                      # Why this matters, what to look at
    block_type: str                       # "research", "follow-up", "prep", "explore"
    suggested_duration_min: Optional[int] = None  # e.g. 30, 60
    related_meeting: Optional[str] = None         # Meeting title if connected
    related_todo: Optional[str] = None            # Todo description if connected


class JournalContext(BaseModel):
    """Parsed evening journal response."""
    raw_text: str
    todos_extracted: List[TodoItem] = []
    focus_areas: List[str] = []           # Free-form areas of interest
    reflections: Optional[str] = None     # General thoughts/context
    received_at: Optional[datetime] = None


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
    # Newsletter sections
    industry_news: List[NewsArticle] = []
    weekly_todos: List[TodoItem] = []
    time_blocks: List[TimeBlock] = []
    journal_context: Optional[JournalContext] = None


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