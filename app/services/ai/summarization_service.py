from typing import List, Dict, Any
import re
import html as html_lib
from openai import OpenAI
from app.core.config import settings
from app.schemas.brief import MeetingEvent, AttendeeInfo


class SummarizationService:
    """Service for generating intelligent summaries using AI."""
    
    def __init__(self):
        # Initialize OpenAI v1 client
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def generate_meeting_brief(self, events: List[MeetingEvent]) -> str:
        """Generate a comprehensive morning brief for all meetings."""
        if not events:
            return "No meetings scheduled for today."
        
        # Prepare context for AI
        context = self._prepare_meeting_context(events)
        
        # Generate brief using OpenAI
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI assistant that creates concise, professional morning briefs for meetings. "
                            "Your goal is to help the user be well-prepared for their meetings by providing:\n"
                            "1. A brief overview of each meeting\n"
                            "2. Key information about attendees\n"
                            "3. Recent news or context about attendees/companies\n"
                            "4. Suggested talking points or conversation starters\n"
                            "5. Any important notes or reminders\n\n"
                            "Keep the tone professional but conversational. Focus on actionable insights."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Generate a morning brief for today's meetings:\n\n{context}",
                    },
                ],
                max_tokens=max(256, settings.brief_summary_length),
                temperature=0.7,
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
        """Generate a concise brief without AI: one-liners per meeting, no locations."""
        def format_time_range(start_dt, end_dt) -> str:
            return f"{start_dt.strftime('%I:%M %p').lstrip('0')}–{end_dt.strftime('%I:%M %p').lstrip('0')}"

        def normalize_name(raw: str) -> str:
            if not raw:
                return ""
            first = raw.strip().split()[0]
            first = re.sub(r"[^A-Za-z'\-]", "", first)
            return first.capitalize() if first else ""

        def is_internal_alias(att) -> bool:
            n = (att.name or "").strip().lower()
            local = (att.email.split('@')[0] if att.email else "").lower()
            if n.startswith("internal") or local.startswith("internal"):
                return True
            return False

        def format_attendees(attendees) -> str:
            display: List[str] = []
            seen = set()
            for att in attendees:
                if not att or is_internal_alias(att):
                    continue
                name = normalize_name(att.name or att.email.split('@')[0])
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                display.append(name)
            if not display:
                return ""
            max_names = 5
            shown = display[:max_names]
            extra = len(display) - len(shown)
            people = ", ".join(shown)
            return f" — {people}{(' +' + str(extra)) if extra > 0 else ''}"

        def strip_html(text: str) -> str:
            if not text:
                return ""
            # Unescape entities, strip tags, collapse whitespace
            unescaped = html_lib.unescape(text)
            no_tags = re.sub(r"<[^>]+>", " ", unescaped)
            clean = " ".join(no_tags.split())
            return clean

        def format_about(description: str, attendees) -> str:
            # 1) Materials
            materials = []
            for att in attendees:
                for u in getattr(att, 'materials', None) or []:
                    if u not in materials:
                        materials.append(u)
            if materials:
                return " — About: Materials: " + " • ".join(materials[:2])

            # 2) Affinity last note / recent context
            base = strip_html(description)
            if not base:
                for att in attendees:
                    if getattr(att, 'last_note_summary', None):
                        base = strip_html(att.last_note_summary)
                        if base:
                            break
                    if getattr(att, 'recent_emails', None):
                        base = strip_html(att.recent_emails[0])
                        if base:
                            break
            # 3) Company website (fallback)
            if not base:
                for att in attendees:
                    if getattr(att, 'website_url', None):
                        base = f"Company site: {att.website_url}"
                        break
            if not base:
                return ""
            clean = base
            if not clean:
                return ""
            snippet = (clean[:120] + "…") if len(clean) > 120 else clean
            return f" — About: {snippet}"

        date_str = events[0].start_time.strftime('%B %d, %Y')
        header = f"Morning Brief - {date_str}\n\n"
        header += f"You have {len(events)} meetings scheduled today:\n\n"

        lines = []
        for event in events:
            time_range = format_time_range(event.start_time, event.end_time)
            attendees_str = format_attendees(event.attendees)
            about_str = format_about(event.description, event.attendees)
            # Single-line, no location
            line = f"📅 {time_range} {event.title}{attendees_str}{about_str}"
            lines.append(line)

        return header + "\n".join(lines) + "\n"
    
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