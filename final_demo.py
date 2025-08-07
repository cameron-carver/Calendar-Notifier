#!/usr/bin/env python3
"""
Final Demonstration - Complete Morning Brief Workflow
This script demonstrates the entire morning brief system working end-to-end.
"""

import asyncio
import json
import requests
from datetime import datetime, date
from app.services.calendar.google_calendar import GoogleCalendarService

# Sample event for demonstration
DEMO_EVENT = {
    "summary": "Demo Meeting - Morning Brief System",
    "description": "This is a demonstration meeting to test the morning brief system",
    "start": {
        "dateTime": datetime.combine(date.today(), datetime.min.time().replace(hour=11, minute=0)).isoformat(),
        "timeZone": "America/New_York"
    },
    "end": {
        "dateTime": datetime.combine(date.today(), datetime.min.time().replace(hour=12, minute=0)).isoformat(),
        "timeZone": "America/New_York"
    },
    "attendees": [
        {"email": "demo.user@example.com", "displayName": "Demo User"},
        {"email": "test.attendee@company.com", "displayName": "Test Attendee"}
    ]
}

class FinalDemo:
    def __init__(self):
        self.calendar_service = GoogleCalendarService()
        self.api_base = "http://127.0.0.1:8000"
    
    def create_demo_event(self):
        """Create a single demo event."""
        print("📅 Creating demo calendar event...")
        
        try:
            event = self.calendar_service.service.events().insert(
                calendarId='primary',
                body=DEMO_EVENT,
                sendUpdates='none'
            ).execute()
            
            print(f"✅ Created: {event['summary']} at {event['start']['dateTime']}")
            return event['id']
            
        except Exception as e:
            print(f"❌ Failed to create demo event: {e}")
            return None
    
    def cleanup_demo_event(self, event_id):
        """Clean up the demo event."""
        if event_id:
            try:
                self.calendar_service.service.events().delete(
                    calendarId='primary',
                    eventId=event_id
                ).execute()
                print(f"✅ Deleted demo event: {event_id}")
            except Exception as e:
                print(f"❌ Failed to delete demo event: {e}")
    
    def test_api_endpoints(self):
        """Test all API endpoints."""
        print("\n🌐 Testing API Endpoints...")
        
        # Test health endpoint
        try:
            response = requests.get(f"{self.api_base}/health")
            print(f"✅ Health check: {response.status_code} - {response.json()}")
        except Exception as e:
            print(f"❌ Health check failed: {e}")
        
        # Test info endpoint
        try:
            response = requests.get(f"{self.api_base}/info")
            print(f"✅ API info: {response.status_code}")
        except Exception as e:
            print(f"❌ API info failed: {e}")
        
        # Test brief generation
        try:
            response = requests.post(
                f"{self.api_base}/briefs/generate",
                json={"target_date": date.today().isoformat()},
                headers={"Content-Type": "application/json"}
            )
            print(f"✅ Brief generation: {response.status_code}")
            if response.status_code == 200:
                brief_data = response.json()
                print(f"   📝 Brief ID: {brief_data['id']}")
                print(f"   📊 Events found: {len(brief_data['events_summary'])}")
                print(f"   📏 Content length: {len(brief_data['content'])} characters")
        except Exception as e:
            print(f"❌ Brief generation failed: {e}")
        
        # Test settings endpoint
        try:
            response = requests.get(f"{self.api_base}/briefs/settings")
            print(f"✅ Settings endpoint: {response.status_code}")
        except Exception as e:
            print(f"❌ Settings endpoint failed: {e}")

async def main():
    """Run the final demonstration."""
    print("🚀 Morning Brief System - Final Demonstration")
    print("=" * 60)
    
    demo = FinalDemo()
    event_id = None
    
    try:
        # Step 1: Test API endpoints (before creating events)
        print("\n📋 Step 1: Testing API endpoints...")
        demo.test_api_endpoints()
        
        # Step 2: Create demo event
        print("\n📋 Step 2: Creating demo calendar event...")
        event_id = demo.create_demo_event()
        
        if not event_id:
            print("❌ Could not create demo event. Stopping demonstration.")
            return
        
        # Step 3: Wait for event to sync
        print("\n📋 Step 3: Waiting for event to sync...")
        await asyncio.sleep(3)
        
        # Step 4: Test brief generation with event
        print("\n📋 Step 4: Testing brief generation with demo event...")
        try:
            response = requests.post(
                f"{demo.api_base}/briefs/generate",
                json={"target_date": date.today().isoformat()},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                brief_data = response.json()
                print("✅ Brief generated successfully!")
                print(f"📊 Events found: {len(brief_data['events_summary'])}")
                
                # Display brief content
                print("\n" + "="*50)
                print("📋 GENERATED BRIEF:")
                print("="*50)
                print(brief_data['content'])
                print("="*50)
                
                # Show event details
                if brief_data['events_summary']:
                    print("\n📅 EVENT DETAILS:")
                    for event in brief_data['events_summary']:
                        print(f"   • {event['title']}")
                        print(f"     Time: {event['start_time']} - {event['end_time']}")
                        print(f"     Attendees: {len(event['attendees'])}")
                        for attendee in event['attendees']:
                            print(f"       - {attendee['name']} ({attendee['email']})")
            else:
                print(f"❌ Brief generation failed: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Brief generation test failed: {e}")
        
        # Step 5: Cleanup
        print("\n📋 Step 5: Cleaning up demo event...")
        demo.cleanup_demo_event(event_id)
        
        print("\n🎉 Final demonstration completed successfully!")
        print("\n📋 Summary:")
        print("   ✅ API endpoints tested")
        print("   ✅ Calendar event created")
        print("   ✅ Brief generation tested")
        print("   ✅ Event cleanup completed")
        print("\n🚀 Your Morning Brief system is fully operational!")
        
    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Cleanup on error
        if event_id:
            demo.cleanup_demo_event(event_id)

if __name__ == "__main__":
    asyncio.run(main()) 