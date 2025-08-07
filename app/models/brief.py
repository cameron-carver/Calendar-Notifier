from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean
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


class UserSettings(Base):
    """Model for storing user preferences."""
    
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    delivery_time = Column(String(5), default="08:00")  # HH:MM format
    timezone = Column(String(50), default="America/New_York")
    email_address = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
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