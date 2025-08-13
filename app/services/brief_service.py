import asyncio
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.brief import Brief, UserSettings
from app.schemas.brief import MeetingEvent, AttendeeInfo, BriefResponse
from app.services.calendar.google_calendar import GoogleCalendarService
from app.services.affinity.affinity_client import AffinityClient
from app.services.news.news_service import NewsService
from app.services.ai.summarization_service import SummarizationService
from app.services.email.gmail_service import GmailService
import pytz
from app.core.config import settings


class BriefService:
    """Main service for generating and sending morning briefs."""
    
    def __init__(self):
        self.calendar_service = GoogleCalendarService()
        self.affinity_client = AffinityClient()
        self.news_service = NewsService()
        self.summarization_service = SummarizationService()
        self.email_service = GmailService()
    
    async def generate_daily_brief(self, target_date: Optional[date] = None) -> BriefResponse:
        """Generate a complete morning brief for the specified date."""
        if target_date is None:
            target_date = date.today()
        
        # Get calendar events
        events = self.calendar_service.get_daily_events(target_date)
        
        if not events:
            # No meetings today
            brief_content = f"No meetings scheduled for {target_date.strftime('%B %d, %Y')}."
            return BriefResponse(
                id=0,
                date=datetime.combine(target_date, datetime.min.time()),
                content=brief_content,
                events_summary=[],
                created_at=datetime.now(),
                is_sent=False
            )
        
        # Enrich attendee information
        enriched_events = await self._enrich_events(events)
        # Add prior meeting history
        await self._enrich_with_history(enriched_events)
        
        # Generate brief content
        brief_content = self.summarization_service.generate_meeting_brief(enriched_events)
        
        # Create brief response
        brief_response = BriefResponse(
            id=0,  # Will be set when saved to database
            date=datetime.combine(target_date, datetime.min.time()),
            content=brief_content,
            events_summary=enriched_events,
            created_at=datetime.now(),
            is_sent=False
        )
        
        return brief_response
    
    async def _enrich_events(self, events: List[MeetingEvent]) -> List[MeetingEvent]:
        """Enrich all events with attendee and news information."""
        enriched_events = []
        
        for event in events:
            # Enrich each attendee
            enriched_attendees = []
            for attendee in event.attendees:
                # Enrich with Affinity data
                enriched_attendee = await self.affinity_client.enrich_attendee_info(attendee)
                
                # Enrich with news (if news API is configured)
                if self.news_service.api_key:
                    attendee_dict = enriched_attendee.dict()
                    attendee_dict = await self.news_service.enrich_attendee_with_news(attendee_dict)
                    enriched_attendee = AttendeeInfo(**attendee_dict)
                
                enriched_attendees.append(enriched_attendee)
            
            # Create enriched event
            enriched_event = MeetingEvent(
                event_id=event.event_id,
                title=event.title,
                start_time=event.start_time,
                end_time=event.end_time,
                attendees=enriched_attendees,
                description=event.description,
                location=event.location
            )
            
            enriched_events.append(enriched_event)
        
        return enriched_events

    async def _enrich_with_history(self, events: List[MeetingEvent]) -> None:
        """Annotate attendees with prior meeting history from Calendar.
        Mutates AttendeeInfo objects in-place.
        """
        if not events:
            return
        # Collect unique attendee emails
        unique_emails = set()
        for ev in events:
            for att in ev.attendees:
                if att and att.email:
                    unique_emails.add(att.email.lower())

        if not unique_emails:
            return

        # Determine lookback window
        tz = pytz.timezone(settings.timezone)
        end_dt = datetime.now(tz)
        start_dt = end_dt - timedelta(days=getattr(settings, 'history_lookback_days', 120))

        # Fetch past events once
        past_events = self.calendar_service.get_events_for_date_range(start_dt, end_dt)

        # Build stats per email
        from collections import defaultdict
        email_to_count = defaultdict(int)
        email_to_last: dict[str, datetime] = {}

        for pev in past_events:
            for patt in getattr(pev, 'attendees', []) or []:
                email = (patt.email or '').lower()
                if not email or email not in unique_emails:
                    continue
                email_to_count[email] += 1
                last = email_to_last.get(email)
                st = getattr(pev, 'start_time', None)
                if isinstance(st, datetime):
                    if (last is None) or (st > last):
                        email_to_last[email] = st

        # Apply to attendees
        for ev in events:
            for att in ev.attendees:
                key = (att.email or '').lower()
                if not key:
                    continue
                if key in email_to_last:
                    att.last_meeting_date = email_to_last[key]
                if key in email_to_count:
                    att.meetings_past_n_days = email_to_count[key]
    
    async def send_morning_brief(self, user_email: str, brief_content: str) -> bool:
        """Send the morning brief via email."""
        try:
            # Create HTML version
            # Regenerate events for today to include structured data for HTML rendering
            events = self.calendar_service.get_daily_events(date.today())
            enriched_events = await self._enrich_events(events) if events else []
            html_content = self.email_service.create_html_brief(brief_content, events=enriched_events)
            
            # Send email
            subject = f"Morning Brief - {datetime.now().strftime('%B %d, %Y')}"
            success = self.email_service.send_morning_brief(
                to_email=user_email,
                subject=subject,
                content=brief_content,
                html_content=html_content
            )
            
            return success
            
        except Exception as e:
            print(f"Error sending morning brief: {e}")
            return False
    
    async def generate_and_send_brief(self, user_email: str, target_date: Optional[date] = None) -> bool:
        """Generate and send a morning brief in one operation."""
        try:
            # Generate brief
            brief_response = await self.generate_daily_brief(target_date)
            
            # Send email
            success = await self.send_morning_brief(user_email, brief_response.content)
            
            return success
            
        except Exception as e:
            print(f"Error generating and sending brief: {e}")
            return False

    async def generate_and_send_if_upcoming(self, user_email: str, window_hours: int = 2) -> bool:
        """Send a brief only if there is an external meeting within the next window hours."""
        try:
            from datetime import timedelta
            target = date.today()
            brief = await self.generate_daily_brief(target)
            has_upcoming = any(True for e in brief.events_summary)
            if not has_upcoming:
                return False
            return await self.send_morning_brief(user_email, brief.content)
        except Exception as e:
            print(f"Error in generate_and_send_if_upcoming: {e}")
            return False
    
    def save_brief_to_database(self, brief_response: BriefResponse, db: Session) -> Brief:
        """Save the brief to the database."""
        brief = Brief(
            date=brief_response.date,
            content=brief_response.content,
            events_summary=[event.dict() for event in brief_response.events_summary],
            created_at=brief_response.created_at,
            is_sent=brief_response.is_sent
        )
        
        db.add(brief)
        db.commit()
        db.refresh(brief)
        
        return brief
    
    def get_user_settings(self, db: Session) -> Optional[UserSettings]:
        """Get user settings from database."""
        return db.query(UserSettings).first()
    
    def update_user_settings(self, settings_data: dict, db: Session) -> UserSettings:
        """Update user settings."""
        settings = db.query(UserSettings).first()
        
        if settings:
            for key, value in settings_data.items():
                setattr(settings, key, value)
        else:
            settings = UserSettings(**settings_data)
            db.add(settings)
        
        db.commit()
        db.refresh(settings)
        
        return settings
    
    def get_brief_history(self, db: Session, limit: int = 10) -> List[Brief]:
        """Get recent brief history."""
        return db.query(Brief).order_by(Brief.created_at.desc()).limit(limit).all() 