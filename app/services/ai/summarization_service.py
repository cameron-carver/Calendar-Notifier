import openai
from typing import List, Dict, Any
from app.core.config import settings
from app.schemas.brief import MeetingEvent, AttendeeInfo


class SummarizationService:
    """Service for generating intelligent summaries using AI."""
    
    def __init__(self):
        openai.api_key = settings.openai_api_key
    
    def generate_meeting_brief(self, events: List[MeetingEvent]) -> str:
        """Generate a comprehensive morning brief for all meetings."""
        if not events:
            return "No meetings scheduled for today."
        
        # Prepare context for AI
        context = self._prepare_meeting_context(events)
        
        # Generate brief using OpenAI
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an AI assistant that creates concise, professional morning briefs for meetings. 
                        Your goal is to help the user be well-prepared for their meetings by providing:
                        1. A brief overview of each meeting
                        2. Key information about attendees
                        3. Recent news or context about attendees/companies
                        4. Suggested talking points or conversation starters
                        5. Any important notes or reminders
                        
                        Keep the tone professional but conversational. Focus on actionable insights."""
                    },
                    {
                        "role": "user",
                        "content": f"Generate a morning brief for today's meetings:\n\n{context}"
                    }
                ],
                max_tokens=settings.brief_summary_length,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating brief with AI: {e}")
            return self._generate_fallback_brief(events)
    
    def _prepare_meeting_context(self, events: List[MeetingEvent]) -> str:
        """Prepare context information for AI summarization."""
        context_parts = []
        
        for event in events:
            event_info = f"Meeting: {event.title}\n"
            event_info += f"Time: {event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}\n"
            
            if event.location:
                event_info += f"Location: {event.location}\n"
            
            if event.description:
                event_info += f"Description: {event.description}\n"
            
            event_info += "Attendees:\n"
            for attendee in event.attendees:
                attendee_info = f"  - {attendee.name} ({attendee.email})"
                if attendee.company:
                    attendee_info += f" from {attendee.company}"
                if attendee.title:
                    attendee_info += f", {attendee.title}"
                attendee_info += "\n"
                
                # Add recent context
                if attendee.recent_emails:
                    attendee_info += f"    Recent context: {' '.join(attendee.recent_emails[:2])}\n"
                
                # Add news articles
                if attendee.news_articles:
                    attendee_info += f"    Recent news: {len(attendee.news_articles)} articles found\n"
                    for article in attendee.news_articles[:2]:
                        attendee_info += f"      - {article.get('title', 'No title')}\n"
                
                event_info += attendee_info
            
            context_parts.append(event_info)
        
        return "\n\n".join(context_parts)
    
    def _generate_fallback_brief(self, events: List[MeetingEvent]) -> str:
        """Generate a basic brief without AI when AI service is unavailable."""
        brief = f"Morning Brief - {events[0].start_time.strftime('%B %d, %Y')}\n\n"
        brief += f"You have {len(events)} meetings scheduled today:\n\n"
        
        for event in events:
            brief += f"📅 {event.title}\n"
            brief += f"   Time: {event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}\n"
            
            if event.location:
                brief += f"   Location: {event.location}\n"
            
            brief += f"   Attendees: {', '.join([a.name for a in event.attendees])}\n"
            
            # Add basic attendee info
            for attendee in event.attendees:
                if attendee.company:
                    brief += f"     - {attendee.name} ({attendee.company})\n"
                else:
                    brief += f"     - {attendee.name}\n"
            
            brief += "\n"
        
        return brief
    
    def generate_attendee_summary(self, attendee: AttendeeInfo) -> str:
        """Generate a summary for a specific attendee."""
        summary_parts = []
        
        summary_parts.append(f"{attendee.name}")
        if attendee.company:
            summary_parts.append(f"from {attendee.company}")
        if attendee.title:
            summary_parts.append(f"({attendee.title})")
        
        summary = " ".join(summary_parts)
        
        # Add recent context
        if attendee.recent_emails:
            summary += f"\nRecent context: {' '.join(attendee.recent_emails[:1])}"
        
        # Add news highlights
        if attendee.news_articles:
            summary += f"\nRecent news: {len(attendee.news_articles)} articles found"
            for article in attendee.news_articles[:1]:
                summary += f"\n- {article.get('title', 'No title')}"
        
        return summary
    
    def generate_conversation_starters(self, attendee: AttendeeInfo) -> List[str]:
        """Generate conversation starters based on attendee information."""
        starters = []
        
        # Company-based starters
        if attendee.company:
            starters.append(f"Ask about recent developments at {attendee.company}")
            starters.append(f"Discuss industry trends affecting {attendee.company}")
        
        # News-based starters
        if attendee.news_articles:
            latest_article = attendee.news_articles[0]
            starters.append(f"Discuss recent news: {latest_article.get('title', '')}")
        
        # Role-based starters
        if attendee.title:
            starters.append(f"Ask about their role as {attendee.title}")
        
        # General starters
        starters.append("Ask about their current priorities and challenges")
        starters.append("Discuss potential collaboration opportunities")
        
        return starters[:3]  # Return top 3 starters 