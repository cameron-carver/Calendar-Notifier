import os
from datetime import datetime, timedelta, date
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.config import settings
from app.schemas.brief import MeetingEvent, AttendeeInfo


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
            # Convert date to datetime
            target_date = datetime.combine(target_date, datetime.min.time())
        
        # Set time range for the entire day
        start_of_day = target_date.replace(hour=0, minute=0, second=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        try:
            # Call the Calendar API
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_of_day.isoformat() + 'Z',
                timeMax=end_of_day.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            meeting_events = []
            for event in events:
                # Skip events without attendees (personal events)
                attendees = event.get('attendees', [])
                if not attendees:
                    continue
                
                # Parse event times
                start_time = datetime.fromisoformat(
                    event['start'].get('dateTime', event['start'].get('date'))
                )
                end_time = datetime.fromisoformat(
                    event['end'].get('dateTime', event['end'].get('date'))
                )
                
                # Extract attendee information
                attendee_infos = []
                for attendee in attendees:
                    if attendee.get('email') and not attendee.get('self', False):
                        attendee_infos.append(AttendeeInfo(
                            email=attendee['email'],
                            name=attendee.get('displayName', attendee['email'].split('@')[0])
                        ))
                
                if attendee_infos:  # Only include events with external attendees
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
    
    def get_events_for_date_range(self, start_date: datetime, end_date: datetime) -> List[MeetingEvent]:
        """Get events for a date range."""
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_date.isoformat() + 'Z',
                timeMax=end_date.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            meeting_events = []
            for event in events:
                attendees = event.get('attendees', [])
                if not attendees:
                    continue
                
                start_time = datetime.fromisoformat(
                    event['start'].get('dateTime', event['start'].get('date'))
                )
                end_time = datetime.fromisoformat(
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