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

    def __init__(self, calendar_ids: Optional[List[str]] = None) -> None:
        """
        Initialize calendar service.

        Args:
            calendar_ids: List of calendar IDs to query.
                         If None, uses global settings.
                         If empty list, uses ['primary'].
        """
        self.service = None
        self._authenticate()

        # Handle calendar IDs
        if calendar_ids is None:
            # Backward compatibility - use global settings
            if settings.google_calendar_ids:
                self.calendar_ids = [c.strip() for c in settings.google_calendar_ids.split(',') if c.strip()]
            else:
                self.calendar_ids = ['primary']
        elif len(calendar_ids) == 0:
            self.calendar_ids = ['primary']
        else:
            self.calendar_ids = calendar_ids
    
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
            meeting_events: List[MeetingEvent] = []
            seen_event_ids = set()  # Deduplicate events across calendars

            # Fetch from each configured calendar
            for calendar_id in self.calendar_ids:
                try:
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
                except HttpError as error:
                    # Log error but continue with other calendars
                    print(f"Failed to fetch calendar {calendar_id}: {error}")
                    continue

                for event in events:
                    # Skip duplicates (same event could appear in multiple calendars)
                    event_id = event.get('id')
                    if event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)

                    # Tag recurring instances (they get lightweight rendering, no enrichment)
                    is_recurring = bool(event.get('recurringEventId') or event.get('recurrence'))

                    attendees = event.get('attendees', [])
                
                    # Parse event times (handles timezone-aware strings)
                    start_time = dateutil_parser.isoparse(
                        event['start'].get('dateTime', event['start'].get('date'))
                    )
                    end_time = dateutil_parser.isoparse(
                        event['end'].get('dateTime', event['end'].get('date'))
                    )
                
                    # Extract names from event title for fallback
                    # Common patterns: "Alice Smith and Bob Jones", "Alice / Bob", "Alice <> Bob"
                    title_names = self._extract_names_from_title(
                        event.get('summary', ''), (calendar_id or '').lower()
                    )

                    # Extract attendee information
                    attendee_infos = []
                    for attendee in attendees:
                        if attendee.get('email'):
                            display = attendee.get('displayName', '')
                            if not display or display == attendee['email'].split('@')[0]:
                                # Try to match from title names
                                local = attendee['email'].split('@')[0].lower()
                                display = self._match_title_name(local, title_names) or display or local
                            attendee_infos.append(AttendeeInfo(
                                email=attendee['email'],
                                name=display,
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
                        is_recurring=is_recurring,
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

    @staticmethod
    def _extract_names_from_title(title: str, owner_email: str) -> List[str]:
        """Extract participant names from an event title.

        Common Calendly/scheduling patterns:
          "Isabela Mendonca and Cameron Carver"
          "Cameron Carver / Andres Kupervaser-Gould (The Network)"
          "Cameron <> Noemi re Togy"
        Returns a list of name strings (excluding the calendar owner).
        """
        if not title:
            return []
        # Split on common delimiters
        parts = re.split(r'\s+(?:and|&|/|<>|,)\s+', title, flags=re.IGNORECASE)
        names = []
        # Derive owner first/last from email for exclusion
        owner_local = owner_email.split('@')[0].lower() if '@' in owner_email else owner_email.lower()
        for part in parts:
            # Strip parenthetical context: "(The Network)", "re Togy"
            clean = re.sub(r'\s*\(.*?\)\s*', ' ', part).strip()
            clean = re.sub(r'\s+re\s+.*$', '', clean, flags=re.IGNORECASE).strip()
            if not clean:
                continue
            # Skip if it looks like the owner
            if owner_local and (
                clean.lower().startswith(owner_local)
                or owner_local.startswith(clean.split()[0].lower())
            ):
                continue
            # Must have at least 2 chars and look like a name (starts with uppercase or has spaces)
            if len(clean) >= 2:
                names.append(clean)
        return names

    @staticmethod
    def _match_title_name(email_local: str, title_names: List[str]) -> Optional[str]:
        """Try to match an email local part to one of the extracted title names.

        Heuristic: if the email local part appears as a prefix of a title name's
        first or last name (case-insensitive), return that title name.
        e.g. email_local="imendonca" → matches "Isabela Mendonca" (last name prefix)
        e.g. email_local="abby" → matches "Abby Nawrocki" (first name prefix)
        """
        if not email_local or not title_names:
            return None
        local = email_local.lower().replace('.', '').replace('_', '').replace('-', '')
        for name in title_names:
            # Check if local matches first name, last name, or first-initial+lastname
            name_parts = name.split()
            for np in name_parts:
                np_clean = np.lower().replace('-', '').replace("'", '')
                if len(np_clean) >= 2 and (local.startswith(np_clean) or np_clean.startswith(local)):
                    return name
            # Also check concatenated: "isabela mendonca" → "isabelamendonca" contains "imendonca"?
            concat = ''.join(p.lower() for p in name_parts)
            if len(local) >= 3 and local in concat:
                return name
            # First initial + last name: "imendonca" → i + mendonca
            if len(name_parts) >= 2:
                fi_last = (name_parts[0][0] + name_parts[-1]).lower().replace('-', '')
                if local == fi_last or fi_last.startswith(local) or local.startswith(fi_last):
                    return name
        return None