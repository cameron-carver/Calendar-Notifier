#!/usr/bin/env python3
"""
Test script for Morning Brief functionality
"""

import asyncio
import os
from datetime import date
from app.services.brief_service import BriefService
from app.core.config import settings


async def test_brief_generation():
    """Test the brief generation functionality."""
    print("🧪 Testing Morning Brief Generation")
    print("=" * 40)
    
    try:
        # Initialize brief service
        print("📋 Initializing Brief Service...")
        brief_service = BriefService()
        print("✅ Brief Service initialized")
        
        # Test calendar integration
        print("\n📅 Testing Calendar Integration...")
        events = brief_service.calendar_service.get_daily_events()
        print(f"✅ Found {len(events)} events for today")
        
        if events:
            print("Sample events:")
            for event in events[:3]:  # Show first 3 events
                print(f"  - {event.title} ({event.start_time.strftime('%I:%M %p')})")
                print(f"    Attendees: {', '.join([a.name for a in event.attendees])}")
        
        # Test brief generation
        print("\n🤖 Testing Brief Generation...")
        brief_response = await brief_service.generate_daily_brief()
        print("✅ Brief generated successfully")
        
        print(f"\n📝 Brief Content Preview:")
        print("-" * 40)
        # Show first 500 characters of the brief
        preview = brief_response.content[:500]
        if len(brief_response.content) > 500:
            preview += "..."
        print(preview)
        print("-" * 40)
        
        # Test Affinity integration (if configured)
        if settings.affinity_api_key and settings.affinity_api_key != "your_affinity_api_key":
            print("\n🔗 Testing Affinity Integration...")
            if events and events[0].attendees:
                attendee = events[0].attendees[0]
                enriched_attendee = await brief_service.affinity_client.enrich_attendee_info(attendee)
                print(f"✅ Enriched attendee: {enriched_attendee.name}")
                if enriched_attendee.company:
                    print(f"   Company: {enriched_attendee.company}")
        
        # Test news integration (if configured)
        if settings.news_api_key:
            print("\n📰 Testing News Integration...")
            if events and events[0].attendees:
                attendee = events[0].attendees[0]
                attendee_dict = attendee.dict()
                enriched_dict = await brief_service.news_service.enrich_attendee_with_news(attendee_dict)
                news_count = len(enriched_dict.get("news_articles", []))
                print(f"✅ Found {news_count} news articles for {attendee.name}")
        else:
            print("\n📰 News API not configured - skipping news integration test")
        
        print("\n🎉 All tests completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_email_service():
    """Test the email service (optional)."""
    print("\n📧 Testing Email Service...")
    
    try:
        brief_service = BriefService()
        
        # Create a test brief
        brief_content = """
Morning Brief - Test

You have 1 meeting scheduled today:

📅 Test Meeting
   Time: 10:00 AM - 11:00 AM
   Location: Conference Room A
   Attendees: John Doe (john@example.com)

This is a test brief to verify email functionality.
        """.strip()
        
        # Test HTML generation
        html_content = brief_service.email_service.create_html_brief(brief_content)
        print("✅ HTML brief generated successfully")
        
        # Note: Email sending is not tested by default to avoid spam
        print("⚠️  Email sending test skipped (to avoid spam)")
        print("   To test email sending, uncomment the code in test_email_service()")
        
        return True
        
    except Exception as e:
        print(f"❌ Email service test failed: {e}")
        return False


def main():
    """Main test function."""
    print("🚀 Morning Brief - Test Suite")
    print("=" * 50)
    
    # Check environment
    print("🔍 Checking environment...")
    required_vars = [
        "GOOGLE_CALENDAR_CREDENTIALS_FILE",
        "AFFINITY_API_KEY", 
        "OPENAI_API_KEY",
        "NEWS_API_KEY",
        "GMAIL_CREDENTIALS_FILE"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var) or os.getenv(var) == f"your_{var.lower()}":
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  Missing or default environment variables: {', '.join(missing_vars)}")
        print("Some tests may be skipped or fail")
    
    # Run tests
    async def run_tests():
        success1 = await test_brief_generation()
        success2 = await test_email_service()
        return success1 and success2
    
    result = asyncio.run(run_tests())
    
    if result:
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    import sys
    main() 