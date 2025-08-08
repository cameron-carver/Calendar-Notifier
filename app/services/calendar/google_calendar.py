import os
from datetime import datetime, timedelta, date, time
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.config import settings
from app.schemas.brief import MeetingEvent, AttendeeInfo
from dateutil import parser as dateutil_parser
import pytz


class GoogleCalendarService:
    """Service for interacting with Google Calendar API."""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
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
                # Call the Calendar API for each calendar
                events_result = self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
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
                    external_attendees = (
                        [a for a in non_owner_attendees if extract_domain(a.email) != owner_domain]
                        if (owner_domain and settings.filter_external_only)
                        else non_owner_attendees
                    )
                    if settings.filter_external_only and len(external_attendees) == 0:
                        continue

                    meeting_events.append(MeetingEvent(
                        event_id=event['id'],
                        title=event.get('summary', 'Untitled Meeting'),
                        start_time=start_time,
                        end_time=end_time,
                        attendees=external_attendees,
                        description=event.get('description'),
                        location=event.get('location')
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
                    meeting_events.append(MeetingEvent(
                        event_id=event['id'],
                        title=event.get('summary', 'Untitled Meeting'),
                        start_time=start_time,
                        end_time=end_time,
                        attendees=attendee_infos,
                        description=event.get('description'),
                        location=event.get('location')
                    ))
            
            return meeting_events
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return [] 