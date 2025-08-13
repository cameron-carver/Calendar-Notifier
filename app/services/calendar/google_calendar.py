import os
from datetime import datetime, timedelta, date, time
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.utils.retry import should_retry_http_error
from app.core.utils.cache import RedisCache, make_key
import time as pytime
from app.core.config import settings
from app.schemas.brief import MeetingEvent, AttendeeInfo
from dateutil import parser as dateutil_parser
import pytz
import re


class GoogleCalendarService:
    """Service for interacting with Google Calendar API."""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self) -> None:
        self.service = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Google Calendar API."""
        creds = None
        
        # Load credentials from file
        if os.path.exists(settings.google_calendar_credentials_file):
            creds = Credentials.from_authorized_user_file(
                settings.google_calendar_credentials_file, 
                self.SCOPES
            )
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # This would typically be done during setup
                # For now, we'll assume credentials are already set up
                raise Exception("Google Calendar credentials not found. Please set up OAuth2 credentials.")
            
            # Save the credentials for the next run
            with open(settings.google_calendar_credentials_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('calendar', 'v3', credentials=creds)
    
    def get_daily_events(self, target_date: Optional[datetime] = None) -> List[MeetingEvent]:
        """Get all events for a specific date."""
        if target_date is None:
            target_date = datetime.now()
        elif isinstance(target_date, date) and not isinstance(target_date, datetime):
            # Convert date to datetime at midnight in configured timezone
            target_date = datetime.combine(target_date, time.min)

        # Localize to configured timezone, then convert to UTC for API query
        local_tz = pytz.timezone(settings.timezone)
        start_local = local_tz.localize(target_date.replace(hour=0, minute=0, second=0, microsecond=0))
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(pytz.UTC)
        end_utc = end_local.astimezone(pytz.UTC)

        # Apply personalization time window (only for today)
        now_local = datetime.now(local_tz)
        if settings.time_window_hours and settings.time_window_hours > 0 and start_local.date() == now_local.date():
            start_local = max(start_local, now_local)
            end_local = min(end_local, start_local + timedelta(hours=settings.time_window_hours))
            start_utc = start_local.astimezone(pytz.UTC)
            end_utc = end_local.astimezone(pytz.UTC)

        # RFC3339 format with Z suffix
        time_min = start_utc.isoformat().replace('+00:00', 'Z')
        time_max = end_utc.isoformat().replace('+00:00', 'Z')
        
        try:
            # Determine calendars to query
            calendar_ids: List[str]
            if settings.google_calendar_ids:
                calendar_ids = [c.strip() for c in settings.google_calendar_ids.split(',') if c.strip()]
            else:
                calendar_ids = ['primary']

            meeting_events: List[MeetingEvent] = []
            for calendar_id in calendar_ids:
                # Cache key per calendar/date window
                cache_key = make_key("gcal", calendar_id or "primary", time_min, time_max)
                cached_items = None
                try:
                    cached_items = RedisCache.get_json_sync(cache_key)
                except Exception:
                    cached_items = None
                if cached_items:
                    events_result = {"items": cached_items}
                else:
                    # Call the Calendar API for each calendar with simple retry
                    attempt = 0
                    while True:
                        try:
                            events_result = self.service.events().list(
                                calendarId=calendar_id,
                                timeMin=time_min,
                                timeMax=time_max,
                                singleEvents=True,
                                orderBy='startTime'
                            ).execute()
                            # Cache items for short TTL to avoid repeated calls in same run
                            items = events_result.get('items', [])
                            try:
                                RedisCache.set_json_sync(cache_key, items, ttl_seconds=600)
                            except Exception:
                                pass
                            break
                        except HttpError as error:
                            attempt += 1
                            if attempt >= 3 or not should_retry_http_error(error):
                                raise
                            pytime.sleep(0.5 * attempt)
                
                events = events_result.get('items', [])
                for event in events:
                    # Filter recurring meetings (exclude instances of recurring series)
                    if settings.filter_exclude_recurring and (event.get('recurringEventId') or event.get('recurrence')):
                        continue
                    attendees = event.get('attendees', [])
                
                    # Parse event times (handles timezone-aware strings)
                    start_time = dateutil_parser.isoparse(
                        event['start'].get('dateTime', event['start'].get('date'))
                    )
                    end_time = dateutil_parser.isoparse(
                        event['end'].get('dateTime', event['end'].get('date'))
                    )
                
                    # Extract attendee information
                    attendee_infos = []
                    for attendee in attendees:
                        if attendee.get('email'):
                            attendee_infos.append(AttendeeInfo(
                                email=attendee['email'],
                                name=attendee.get('displayName', attendee['email'].split('@')[0])
                            ))

                    # Smart filter 1: only include if there is at least one attendee besides the calendar owner
                    owner_identifier = (calendar_id or '').lower()
                    non_owner_attendees = [a for a in attendee_infos if a.email.lower() != owner_identifier]
                    if settings.filter_require_non_owner_attendee and len(non_owner_attendees) == 0:
                        continue

                    # Smart filter 2: external meetings only — require at least one attendee whose domain differs from owner's
                    def extract_domain(email_value: str) -> str:
                        try:
                            return email_value.split('@', 1)[1].lower()
                        except Exception:
                            return ''

                    owner_domain = extract_domain(owner_identifier) if '@' in owner_identifier else ''
                    # Internal domains set
                    internal_domains_set = set(d.strip().lower() for d in (settings.internal_domains or '').split(',') if d.strip())
                    external_attendees = (
                        [a for a in non_owner_attendees if extract_domain(a.email) != owner_domain]
                        if (owner_domain and settings.filter_external_only)
                        else non_owner_attendees
                    )
                    # If internal domains configured, treat same-domain as internal and prefer externals
                    if internal_domains_set:
                        externals = [a for a in external_attendees if extract_domain(a.email) not in internal_domains_set]
                        external_attendees = externals if externals else external_attendees

                    if settings.filter_external_only and len(external_attendees) == 0:
                        continue

                    # Quick links and duration
                    meeting_url = self._extract_meeting_url(event)
                    calendar_url = event.get('htmlLink')
                    duration_minutes = int((end_time - start_time).total_seconds() // 60)

                    meeting_events.append(MeetingEvent(
                        event_id=event['id'],
                        title=event.get('summary', 'Untitled Meeting'),
                        start_time=start_time,
                        end_time=end_time,
                        attendees=external_attendees,
                        description=event.get('description'),
                        location=event.get('location'),
                        meeting_url=meeting_url,
                        calendar_url=calendar_url,
                        duration_minutes=duration_minutes,
                    ))
            
            return meeting_events
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []
    
    def get_events_for_date_range(self, start_date: datetime, end_date: datetime) -> List[MeetingEvent]:
        """Get events for a date range."""
        # Ensure timezone-aware conversion to UTC
        local_tz = pytz.timezone(settings.timezone)
        if start_date.tzinfo is None:
            start_date = local_tz.localize(start_date)
        if end_date.tzinfo is None:
            end_date = local_tz.localize(end_date)

        start_utc = start_date.astimezone(pytz.UTC)
        end_utc = end_date.astimezone(pytz.UTC)
        time_min = start_utc.isoformat().replace('+00:00', 'Z')
        time_max = end_utc.isoformat().replace('+00:00', 'Z')
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            meeting_events = []
            for event in events:
                attendees = event.get('attendees', [])
                if not attendees:
                    continue
                
                start_time = dateutil_parser.isoparse(
                    event['start'].get('dateTime', event['start'].get('date'))
                )
                end_time = dateutil_parser.isoparse(
                    event['end'].get('dateTime', event['end'].get('date'))
                )
                
                attendee_infos = []
                for attendee in attendees:
                    if attendee.get('email') and not attendee.get('self', False):
                        attendee_infos.append(AttendeeInfo(
                            email=attendee['email'],
                            name=attendee.get('displayName', attendee['email'].split('@')[0])
                        ))
                
                if attendee_infos:
                    meeting_url = self._extract_meeting_url(event)
                    calendar_url = event.get('htmlLink')
                    duration_minutes = int((end_time - start_time).total_seconds() // 60)
                    meeting_events.append(MeetingEvent(
                        event_id=event['id'],
                        title=event.get('summary', 'Untitled Meeting'),
                        start_time=start_time,
                        end_time=end_time,
                        attendees=attendee_infos,
                        description=event.get('description'),
                        location=event.get('location'),
                        meeting_url=meeting_url,
                        calendar_url=calendar_url,
                        duration_minutes=duration_minutes,
                    ))

            return meeting_events
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []

    def _extract_meeting_url(self, event: dict) -> Optional[str]:
        """Best-effort extraction of a conferencing URL from a Calendar event."""
        # Google Meet direct fields
        url = event.get('hangoutLink') or event.get('hangoutLink')
        if url:
            return url
        conf = event.get('conferenceData') or {}
        for ep in conf.get('entryPoints', []) or []:
            if isinstance(ep, dict) and ep.get('entryPointType') in ('video', 'more'):
                uri = ep.get('uri') or ep.get('url')
                if isinstance(uri, str) and uri.startswith('http'):
                    return uri
        # Scan description/location for common providers
        text = ' '.join([
            str(event.get('description') or ''),
            str(event.get('location') or ''),
        ])
        pattern = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
        for m in pattern.finditer(text):
            u = m.group(0)
            if any(p in u.lower() for p in ("meet.google.com", "zoom.us", "teams.microsoft.com", "webex.com")):
                return u
        return None