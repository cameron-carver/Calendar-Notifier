from sqlalchemy import Column, Integer, String, DateTime, Date, Text, JSON, Boolean, Float, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class Brief(Base):
    """Model for storing generated briefs."""

    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)
    content = Column(Text, nullable=False)
    events_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    is_sent = Column(Boolean, default=False)

    # Executive ownership (nullable for backward compatibility)
    executive_id = Column(Integer, nullable=True, index=True)


class UserSettings(Base):
    """Model for storing user preferences."""

    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Basic delivery settings
    delivery_time = Column(String(5), default="08:00")  # HH:MM format (kept for backward compatibility)
    delivery_schedule = Column(JSON, nullable=True)  # Day-specific times: {"monday": "08:00", "tuesday": "07:30", "default": "08:00"}
    timezone = Column(String(50), default="America/New_York")
    email_address = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    # Content preferences
    content_depth = Column(String(20), default="standard")  # "quick" | "standard" | "detailed"
    time_window_hours = Column(Integer, nullable=True)  # Override global setting (0 = all day)

    # Feature toggles (None = use global default from .env)
    enable_ai_prep = Column(Boolean, nullable=True)
    enable_news = Column(Boolean, nullable=True)
    enable_meeting_history = Column(Boolean, nullable=True)
    enable_affinity_data = Column(Boolean, nullable=True)
    enable_web_enrichment = Column(Boolean, nullable=True)

    # Filter preferences
    filter_require_non_owner = Column(Boolean, nullable=True)
    filter_external_only = Column(Boolean, nullable=True)
    filter_exclude_recurring = Column(Boolean, nullable=True)

    # Content limits
    max_news_articles = Column(Integer, nullable=True)
    talking_points_enabled = Column(Boolean, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MeetingEvent(Base):
    """Model for storing meeting event details."""

    __tablename__ = "meeting_events"

    id = Column(Integer, primary_key=True, index=True)
    brief_id = Column(Integer, nullable=False, index=True)
    event_id = Column(String(255), nullable=False)  # Google Calendar event ID
    title = Column(String(500), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    attendees = Column(JSON, nullable=True)  # List of attendee emails
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FilterPreset(Base):
    """Model for storing saved filter presets for quick switching."""

    __tablename__ = "filter_presets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # Future: FK to UserSettings
    name = Column(String(100), nullable=False)  # "Founders Only", "First Meetings"
    description = Column(String(255), nullable=True)

    # Filter configuration stored as JSON
    # Example: {
    #   "require_non_owner": true,
    #   "external_only": true,
    #   "exclude_recurring": true,
    #   "persona_types": ["founder", "lp"],
    #   "time_window_hours": 4
    # }
    filters = Column(JSON, nullable=False)

    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class BriefMetrics(Base):
    """Model for tracking brief generation metrics for usage dashboard."""

    __tablename__ = "brief_metrics"

    id = Column(Integer, primary_key=True, index=True)
    brief_id = Column(Integer, nullable=False, index=True)  # FK to Brief

    # Generation metrics
    meetings_processed = Column(Integer, default=0)
    meetings_enriched = Column(Integer, default=0)
    meetings_with_ai_prep = Column(Integer, default=0)

    # API usage tracking
    affinity_api_calls = Column(Integer, default=0)
    openai_tokens_used = Column(Integer, default=0)
    news_api_calls = Column(Integer, default=0)

    # Enrichment success rates
    linkedin_found = Column(Integer, default=0)
    news_articles_found = Column(Integer, default=0)
    company_data_found = Column(Integer, default=0)

    # Performance metrics
    generation_time_seconds = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Executive(Base):
    """Model for storing executive profiles in EA mode."""

    __tablename__ = "executives"

    id = Column(Integer, primary_key=True, index=True)

    # Executive identity
    name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, unique=True, index=True)

    # Calendar configuration
    google_calendar_ids = Column(JSON, nullable=False)  # List of calendar IDs to aggregate
    timezone = Column(String(50), default="America/New_York")

    # Delivery preferences
    delivery_time = Column(String(5), default="08:00")  # HH:MM format
    delivery_schedule = Column(JSON, nullable=True)  # Day-specific times
    email_recipient = Column(String(255), nullable=True)  # Override email (for EA)

    # Content preferences (inherits from global, can override)
    content_depth = Column(String(20), default="standard")
    time_window_hours = Column(Integer, nullable=True)

    # Feature toggles (None = use global default)
    enable_ai_prep = Column(Boolean, nullable=True)
    enable_news = Column(Boolean, nullable=True)
    enable_meeting_history = Column(Boolean, nullable=True)
    enable_affinity_data = Column(Boolean, nullable=True)
    enable_web_enrichment = Column(Boolean, nullable=True)

    # Filter preferences
    filter_require_non_owner = Column(Boolean, nullable=True)
    filter_external_only = Column(Boolean, nullable=True)
    filter_exclude_recurring = Column(Boolean, nullable=True)

    # Profile context
    focus_area = Column(Text, nullable=True)  # Investment focus, expertise areas
    linkedin_url = Column(String(500), nullable=True)
    internal_domains = Column(JSON, nullable=True)  # List of company/fund domains

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MeetingAnnotation(Base):
    """Model for EA-added context and notes for meetings."""

    __tablename__ = "meeting_annotations"

    id = Column(Integer, primary_key=True, index=True)

    # Links to executive and meeting
    executive_id = Column(Integer, nullable=False, index=True)  # FK to Executive
    event_id = Column(String(255), nullable=False, index=True)  # Google Calendar event ID

    # Priority classification
    priority = Column(String(20), default="normal")  # "critical" | "high" | "normal" | "low"

    # EA notes
    prep_notes = Column(Text, nullable=True)  # Context EA wants executive to know
    action_before_meeting = Column(Text, nullable=True)  # Things to do before meeting

    # Post-meeting tracking
    post_meeting_notes = Column(Text, nullable=True)
    decisions_made = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)  # List of action items with owners

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PersonRelationship(Base):
    """Model for tracking relationships between executives and meeting attendees."""

    __tablename__ = "person_relationships"

    id = Column(Integer, primary_key=True, index=True)

    # Who and with whom
    executive_id = Column(Integer, nullable=False, index=True)  # FK to Executive
    person_email = Column(String(255), nullable=False, index=True)  # Attendee email
    person_name = Column(String(255), nullable=True)  # Cached name
    person_company = Column(String(255), nullable=True)  # Cached company

    # Relationship metadata
    relationship_strength = Column(String(20), default="new")  # "new" | "developing" | "strong" | "key"
    relationship_status = Column(String(50), nullable=True)  # "investor", "founder", "advisor", "co-investor"
    relationship_notes = Column(Text, nullable=True)  # EA context about the relationship

    # Personal details
    personal_details = Column(JSON, nullable=True)  # Interests, family, preferences
    linkedin_url = Column(String(500), nullable=True)

    # Meeting history
    first_met_date = Column(DateTime, nullable=True)
    last_met_date = Column(DateTime, nullable=True)
    total_meetings = Column(Integer, default=0)

    # Follow-up tracking
    last_follow_up = Column(DateTime, nullable=True)
    next_follow_up = Column(DateTime, nullable=True)
    follow_up_cadence_days = Column(Integer, nullable=True)  # Suggested cadence

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class JournalEntry(Base):
    """Model for storing evening journal prompts and replies.

    Each entry represents one day in the journal loop:
    7pm → prompt sent → user replies → 8am next day picks it up.
    """

    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)

    # The day this journal covers
    date = Column(Date, nullable=False, index=True)

    # Gmail tracking for reply detection
    prompt_message_id = Column(String(255), nullable=True)  # Gmail message ID of sent prompt
    prompt_thread_id = Column(String(255), nullable=True)    # Gmail thread ID for finding replies
    prompt_sent_at = Column(DateTime(timezone=True), nullable=True)

    # User's reply
    response_text = Column(Text, nullable=True)              # Raw reply text
    response_received_at = Column(DateTime(timezone=True), nullable=True)

    # AI-parsed structure from reply
    extracted_todos = Column(JSON, nullable=True)            # List of action items
    extracted_focus_areas = Column(JSON, nullable=True)      # List of research/exploration areas
    extracted_reflections = Column(Text, nullable=True)      # General thoughts/context

    # Executive ownership (nullable for single-user mode)
    executive_id = Column(
        Integer,
        ForeignKey("executives.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())