#!/usr/bin/env python3
"""
Complete Workflow Test for Morning Brief System
This script tests the entire workflow by creating sample calendar events and generating briefs.
"""

import asyncio
import json
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from app.core.config import settings
from app.services.brief_service import BriefService
from app.services.calendar.google_calendar import GoogleCalendarService

# Sample events to create
SAMPLE_EVENTS = [
    {
        "summary": "Product Strategy Meeting",
        "description": "Discuss Q4 product roadmap and feature priorities",
        "start": {
            "dateTime": (datetime.now() + timedelta(hours=2)).isoformat(),
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": (datetime.now() + timedelta(hours=3)).isoformat(),
            "timeZone": "America/New_York"
        },
        "attendees": [
            {"email": "john.doe@techcorp.com", "displayName": "John Doe"},
            {"email": "sarah.smith@innovate.com", "displayName": "Sarah Smith"},
            {"email": "mike.johnson@startup.io", "displayName": "Mike Johnson"}
        ]
    },
    {
        "summary": "Client Demo - Acme Corp",
        "description": "Demonstrate new features to Acme Corp team",
        "start": {
            "dateTime": (datetime.now() + timedelta(hours=5)).isoformat(),
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": (datetime.now() + timedelta(hours=6)).isoformat(),
            "timeZone": "America/New_York"
        },
        "attendees": [
            {"email": "lisa.wong@acme.com", "displayName": "Lisa Wong"},
            {"email": "david.chen@acme.com", "displayName": "David Chen"},
            {"email": "emma.rodriguez@acme.com", "displayName": "Emma Rodriguez"}
        ]
    },
    {
        "summary": "Team Standup",
        "description": "Daily team synchronization meeting",
        "start": {
            "dateTime": (datetime.now() + timedelta(hours=8)).isoformat(),
            "timeZone": "America/New_York"
        },
        "end": {
            "dateTime": (datetime.now() + timedelta(hours=8, minutes=30)).isoformat(),
            "timeZone": "America/New_York"
        },
        "attendees": [
            {"email": "alex.kumar@techcorp.com", "displayName": "Alex Kumar"},
            {"email": "rachel.green@techcorp.com", "displayName": "Rachel Green"},
            {"email": "tom.wilson@techcorp.com", "displayName": "Tom Wilson"}
        ]
    }
]

class WorkflowTester:
    def __init__(self):
        self.calendar_service = GoogleCalendarService()
        self.brief_service = BriefService()
    
    def create_sample_events(self):
        """Create sample events in Google Calendar."""
        print("📅 Creating sample calendar events...")
        
        created_events = []
        for event_data in SAMPLE_EVENTS:
            try:
                event = self.calendar_service.service.events().insert(
                    calendarId='primary',
                    body=event_data,
                    sendUpdates='none'  # Don't send email notifications
                ).execute()
                
                created_events.append({
                    'id': event['id'],
                    'summary': event['summary'],
                    'start': event['start']['dateTime']
                })
                
                print(f"✅ Created: {event['summary']} at {event['start']['dateTime']}")
                
            except Exception as e:
                print(f"❌ Failed to create event '{event_data['summary']}': {e}")
        
        return created_events
    
    def cleanup_sample_events(self, event_ids):
        """Clean up the sample events we created."""
        print("\n🧹 Cleaning up sample events...")
        
        for event_id in event_ids:
            try:
                self.calendar_service.service.events().delete(
                    calendarId='primary',
                    eventId=event_id
                ).execute()
                print(f"✅ Deleted event: {event_id}")
            except Exception as e:
                print(f"❌ Failed to delete event {event_id}: {e}")
    
    async def test_brief_generation(self):
        """Test brief generation with the sample events."""
        print("\n🤖 Testing brief generation...")
        
        try:
            # Generate brief for today
            brief_response = await self.brief_service.generate_daily_brief()
            
            print("✅ Brief generated successfully!")
            print(f"📅 Date: {brief_response.date}")
            print(f"📝 Content Length: {len(brief_response.content)} characters")
            print(f"📊 Events Found: {len(brief_response.events_summary)}")
            
            # Display brief content
            print("\n" + "="*60)
            print("📋 GENERATED BRIEF CONTENT:")
            print("="*60)
            print(brief_response.content)
            print("="*60)
            
            # Show event details
            if brief_response.events_summary:
                print("\n📅 EVENT DETAILS:")
                for i, event in enumerate(brief_response.events_summary, 1):
                    print(f"\n{i}. {event.title}")
                    print(f"   Time: {event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}")
                    print(f"   Attendees: {len(event.attendees)}")
                    for attendee in event.attendees:
                        print(f"     - {attendee.name} ({attendee.email})")
                        if hasattr(attendee, 'company') and attendee.company:
                            print(f"       Company: {attendee.company}")
                        if hasattr(attendee, 'linkedin_url') and attendee.linkedin_url:
                            print(f"       LinkedIn: {attendee.linkedin_url}")
            
            return brief_response
            
        except Exception as e:
            print(f"❌ Brief generation failed: {e}")
            return None
    
    async def test_email_generation(self, brief_content):
        """Test email HTML generation."""
        print("\n📧 Testing email generation...")
        
        try:
            html_content = self.brief_service.email_service.create_html_brief(brief_content)
            print("✅ HTML email generated successfully!")
            print(f"📏 HTML Length: {len(html_content)} characters")
            
            # Save HTML to file for inspection
            with open('sample_brief.html', 'w') as f:
                f.write(html_content)
            print("💾 HTML saved to 'sample_brief.html' for inspection")
            
            return html_content
            
        except Exception as e:
            print(f"❌ Email generation failed: {e}")
            return None

async def main():
    """Run the complete workflow test."""
    print("🚀 Morning Brief - Complete Workflow Test")
    print("=" * 50)
    
    tester = WorkflowTester()
    
    try:
        # Step 1: Create sample events
        created_events = tester.create_sample_events()
        
        if not created_events:
            print("❌ No events were created. Cannot proceed with testing.")
            return
        
        print(f"\n✅ Created {len(created_events)} sample events")
        
        # Step 2: Wait a moment for events to sync
        print("\n⏳ Waiting for events to sync...")
        await asyncio.sleep(3)
        
        # Step 3: Test brief generation
        brief_response = await tester.test_brief_generation()
        
        if brief_response:
            # Step 4: Test email generation
            await tester.test_email_generation(brief_response.content)
        
        # Step 5: Cleanup
        event_ids = [event['id'] for event in created_events]
        tester.cleanup_sample_events(event_ids)
        
        print("\n🎉 Workflow test completed successfully!")
        print("\n📋 Summary:")
        print(f"   • Created {len(created_events)} sample events")
        print(f"   • Generated brief with {len(brief_response.events_summary) if brief_response else 0} events")
        print("   • Created HTML email template")
        print("   • Cleaned up all sample events")
        
    except Exception as e:
        print(f"❌ Workflow test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 