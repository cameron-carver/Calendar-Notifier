from typing import List, Dict, Any, Optional
import json
import re
import html as html_lib
from openai import OpenAI
from app.core.config import settings
from app.core.owner_profile import owner_profile
from app.schemas.brief import MeetingEvent, AttendeeInfo


class SummarizationService:
    """Service for generating intelligent, persona-aware meeting briefs."""

    def __init__(self):
        # Initialize OpenAI v1 client
        self.client = OpenAI(api_key=settings.openai_api_key)

    # ------------------------------------------------------------------
    # LLM-based brief
    # ------------------------------------------------------------------

    def generate_meeting_brief(self, events: List[MeetingEvent]) -> str:
        """Generate a comprehensive morning brief for all meetings."""
        if not events:
            return "No meetings scheduled for today."

        # Prepare context for AI
        context = self._prepare_meeting_context(events)

        # Build persona-aware system prompt
        system_prompt = self._build_system_prompt()

        # Generate brief using OpenAI
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Generate a morning brief for today's meetings:\n\n{context}",
                    },
                ],
                max_tokens=max(512, settings.brief_summary_length * 2),
                temperature=0.7,
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"Error generating brief with AI: {e}")
            return self._generate_fallback_brief(events)

    # ------------------------------------------------------------------
    # Per-meeting structured AI prep
    # ------------------------------------------------------------------

    def generate_per_meeting_prep(self, event: MeetingEvent) -> Optional[Dict[str, Any]]:
        """Generate structured prep for a single meeting.

        Returns a dict with keys: purpose, prep_actions, key_question
        or None on failure.
        """
        context = self._build_meeting_context(event)
        system = self._build_prep_system_prompt()

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": context},
                ],
                response_format={"type": "json_object"},
                max_tokens=400,
                temperature=0.5,
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
            # Validate expected keys
            if isinstance(data, dict) and "purpose" in data:
                return {
                    "purpose": data.get("purpose", ""),
                    "prep_actions": data.get("prep_actions", [])[:4],
                    "key_question": data.get("key_question", ""),
                }
        except (json.JSONDecodeError, Exception) as e:
            print(f"[AI Prep] Error for '{event.title}': {e}")
        return None

    def _build_prep_system_prompt(self) -> str:
        """Build the system prompt for per-meeting structured prep."""
        owner_block = ""
        if owner_profile.name:
            owner_block = (
                f"You are preparing {owner_profile.name} "
                f"({owner_profile.title} at {owner_profile.company}) for a meeting.\n"
            )
            if owner_profile.focus:
                owner_block += f"{owner_profile.company} focuses on: {owner_profile.focus}.\n"

        return (
            f"{owner_block}\n"
            "Analyze the meeting data below and return a JSON object with exactly these keys:\n\n"
            '{\n'
            '  "purpose": "One sentence on why this meeting is likely happening",\n'
            '  "prep_actions": ["Action 1", "Action 2", "Action 3"],\n'
            '  "key_question": "The single most important question to ask"\n'
            '}\n\n'
            "RULES FOR prep_actions — tailor to the attendee persona:\n"
            "- FOUNDER: What do they build? Does it fit the thesis? Check for any deck/materials. "
            "Note their stage and what they might be raising.\n"
            "- COINVESTOR: Think about deal flow to share, portfolio company intros, market themes to discuss.\n"
            "- LP: Have fund metrics and recent portfolio wins ready. Think about relationship health "
            "and any updates to proactively share.\n"
            "- SERVICE_PROVIDER: Know the engagement status, any open deliverables or decisions needed.\n"
            "- CORPORATE: Think about partnership angles with portfolio companies, strategic relevance.\n"
            "- INTERNAL: Keep it short — just note the likely topic.\n"
            "- UNKNOWN: Focus on who they are and the likely meeting purpose.\n\n"
            "CRITICAL:\n"
            "- ONLY use information provided. Do NOT invent data.\n"
            "- Be specific and concise. Each prep_action should be one sentence.\n"
            "- The key_question should be something that drives the meeting forward.\n"
            "- Return ONLY valid JSON, no markdown."
        )

    def _build_meeting_context(self, event: MeetingEvent) -> str:
        """Build context string for a single meeting's AI prep."""
        parts = []
        parts.append(f"Meeting: {event.title}")
        parts.append(
            f"Time: {event.start_time.strftime('%I:%M %p')} - "
            f"{event.end_time.strftime('%I:%M %p')} "
            f"({event.duration_minutes or '?'} min)"
        )

        if event.description:
            desc = event.description[:400]
            parts.append(f"Description: {desc}")

        for att in event.attendees:
            persona = (att.persona_type or "unknown").upper()
            line = f"\nAttendee [{persona}]: {att.name} ({att.email})"
            if att.title:
                line += f"\n  Title: {att.title}"
            if att.company:
                line += f"\n  Company: {att.company}"
            if att.company_description:
                line += f"\n  About company: {att.company_description[:200]}"

            # Affinity pipeline
            if att.affinity_stage:
                line += f"\n  CRM Stage: {att.affinity_stage}"
                if att.affinity_list_name:
                    line += f" (in '{att.affinity_list_name}')"

            # Relationship history
            history = []
            if att.last_meeting_date:
                try:
                    dt = att.last_meeting_date
                    if isinstance(dt, str):
                        from dateutil import parser as _p
                        dt = _p.isoparse(dt)
                    history.append(f"Last met: {dt.strftime('%b %d, %Y')}")
                except Exception:
                    pass
            if att.meetings_past_n_days:
                history.append(f"{att.meetings_past_n_days}x in past {getattr(settings, 'history_lookback_days', 120)} days")
            if not history:
                history.append("First meeting or no prior record")
            line += f"\n  History: {', '.join(history)}"

            # Recent meeting titles
            if att.recent_meeting_titles:
                titles = att.recent_meeting_titles[:3]
                line += f"\n  Recent meetings: {'; '.join(titles)}"

            # CRM notes
            if att.last_note_summary:
                line += f"\n  Last CRM note: {att.last_note_summary[:200]}"

            # Materials
            if att.materials:
                line += f"\n  Materials: {', '.join(att.materials[:3])}"

            parts.append(line)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Monolithic brief (kept for plain-text MIME part)
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build an owner-aware system prompt with persona guidance."""
        owner_block = ""
        if owner_profile.name:
            owner_block = (
                f"You are a meeting preparation assistant for {owner_profile.summary_line()}.\n"
            )
            if owner_profile.focus:
                owner_block += f"{owner_profile.company} focuses on: {owner_profile.focus}.\n"
            owner_block += "\n"

        return (
            f"{owner_block}"
            "Create a concise, professional morning brief. For each meeting provide:\n"
            "1. Meeting context and likely purpose (inferred from title, description, attendees)\n"
            "2. Who they are — tailor depth to the attendee's persona type:\n"
            "   - FOUNDER: What their company does, stage, relevance to the owner's thesis\n"
            "   - COINVESTOR: Their fund and focus, any shared deal-flow angles\n"
            "   - LP: Relationship context, keep it light on fund details\n"
            "   - CORPORATE: Their company's relevance, partnership or portfolio angles\n"
            "   - SERVICE_PROVIDER: What service they handle, any pending items\n"
            "   - INTERNAL: Skip detailed prep, just note the topic\n"
            "3. Relationship status — when you last met, how often, last CRM note\n"
            "4. 2-3 specific talking points from the owner's perspective\n\n"
            "CRITICAL RULES:\n"
            "- ONLY use information explicitly provided in the meeting data below.\n"
            "- If a field says 'None' or is missing, say so — do NOT invent dates, history, titles, or company details.\n"
            "- If you have no data on an attendee, say 'No CRM data available' rather than guessing.\n"
            "- If History shows last_met=None, say 'First meeting or no prior record' — do NOT fabricate past meetings.\n\n"
            "Keep the tone professional but conversational. Focus on actionable insights.\n"
            "If persona type is INTERNAL, keep that meeting's section very brief."
        )

    def _prepare_meeting_context(self, events: List[MeetingEvent]) -> str:
        """Prepare context information for AI summarization, including persona labels."""
        # Owner context header
        parts = []
        if owner_profile.name:
            parts.append(
                f"[Owner] {owner_profile.summary_line()}"
                + (f" | Focus: {owner_profile.focus}" if owner_profile.focus else "")
            )
            parts.append("")

        for event in events:
            event_info = f"Meeting: {event.title}\n"
            event_info += f"Time: {event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}\n"

            if event.description:
                # Truncate long descriptions
                desc = event.description[:300]
                event_info += f"Description: {desc}\n"

            event_info += "Attendees:\n"
            for attendee in event.attendees:
                persona_label = (attendee.persona_type or "unknown").upper()
                attendee_info = f"  - [{persona_label}] {attendee.name} ({attendee.email})"
                if attendee.company:
                    attendee_info += f" from {attendee.company}"
                if attendee.title:
                    attendee_info += f", {attendee.title}"
                attendee_info += "\n"

                # Company description
                if attendee.company_description:
                    desc_short = attendee.company_description[:150]
                    attendee_info += f"    Company: {desc_short}\n"

                # Relationship history
                history_bits = []
                if attendee.last_meeting_date:
                    try:
                        dt = attendee.last_meeting_date
                        if isinstance(dt, str):
                            from dateutil import parser as _p
                            dt = _p.isoparse(dt)
                        history_bits.append(f"last met {dt.strftime('%b %d, %Y')}")
                    except Exception:
                        pass
                if attendee.meetings_past_n_days:
                    history_bits.append(f"{attendee.meetings_past_n_days}x in last {settings.history_lookback_days} days")
                if history_bits:
                    attendee_info += f"    History: {', '.join(history_bits)}\n"

                # Recent context from Affinity
                if attendee.recent_emails:
                    attendee_info += f"    Recent context: {' '.join(attendee.recent_emails[:2])}\n"

                # Last CRM note
                if attendee.last_note_summary:
                    note_short = attendee.last_note_summary[:200]
                    attendee_info += f"    Last CRM note: {note_short}\n"

                # News articles
                if attendee.news_articles:
                    attendee_info += f"    Recent news: {len(attendee.news_articles)} articles\n"
                    for article in attendee.news_articles[:2]:
                        attendee_info += f"      - {article.get('title', 'No title')}\n"

                event_info += attendee_info

            parts.append(event_info)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Fallback brief (rule-based, no LLM)
    # ------------------------------------------------------------------

    def _generate_fallback_brief(self, events: List[MeetingEvent]) -> str:
        """Generate a concise brief without AI: one-liners per meeting with persona labels."""
        def format_time_range(start_dt, end_dt) -> str:
            return f"{start_dt.strftime('%I:%M %p').lstrip('0')}\u2013{end_dt.strftime('%I:%M %p').lstrip('0')}"

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
                # Add persona tag
                persona = getattr(att, 'persona_type', None) or ''
                tag = ''
                if persona and persona not in ('unknown', 'internal'):
                    labels = {
                        'founder': 'F', 'coinvestor': 'VC',
                        'lp': 'LP', 'corporate': 'Corp', 'service_provider': 'Svc',
                    }
                    tag = f"[{labels.get(persona, '')}]" if labels.get(persona) else ''
                display.append(f"{tag}{name}" if tag else name)
            if not display:
                return ""
            max_names = 5
            shown = display[:max_names]
            extra = len(display) - len(shown)
            people = ", ".join(shown)
            return f" \u2014 {people}{(' +' + str(extra)) if extra > 0 else ''}"

        def strip_html(text: str) -> str:
            if not text:
                return ""
            unescaped = html_lib.unescape(text)
            no_tags = re.sub(r"<[^>]+>", " ", unescaped)
            clean = " ".join(no_tags.split())
            return clean

        def format_about(_description: str, attendees) -> str:
            # 1) Company website from attendee (preferred)
            website = None
            for att in attendees:
                website = getattr(att, 'website_url', None)
                if website:
                    break
            if not website:
                for att in attendees:
                    email = getattr(att, 'email', '') or ''
                    if '@' in email:
                        domain = email.split('@', 1)[1]
                        website = f"https://{domain}"
                        break
            if website:
                return f" \u2014 About: Company site: {website}"

            # 2) Affinity data
            base = None
            for att in attendees:
                if getattr(att, 'last_note_summary', None):
                    base = strip_html(att.last_note_summary)
                    if base:
                        break
            if not base:
                for att in attendees:
                    if getattr(att, 'recent_emails', None):
                        base = strip_html(att.recent_emails[0])
                        if base:
                            break
            if not base:
                materials = []
                for att in attendees:
                    for u in getattr(att, 'materials', None) or []:
                        if u not in materials:
                            materials.append(u)
                if materials:
                    return " \u2014 About: Materials: " + " \u2022 ".join(materials[:2])

            if not base:
                return ""
            snippet = (base[:120] + "\u2026") if len(base) > 120 else base
            return f" \u2014 About: {snippet}"

        date_str = events[0].start_time.strftime('%B %d, %Y')
        owner_line = f" for {owner_profile.short_name}" if owner_profile.short_name else ""
        header = f"Morning Brief{owner_line} - {date_str}\n\n"
        header += f"You have {len(events)} meetings scheduled today:\n\n"

        lines = []
        for event in events:
            time_range = format_time_range(event.start_time, event.end_time)
            attendees_str = format_attendees(event.attendees)
            about_str = format_about(event.description, event.attendees)
            line = f"\U0001f4c5 {time_range} {event.title}{attendees_str}{about_str}"
            # Optional talking points (rule-based)
            if getattr(settings, 'enable_talking_points', False) and not getattr(settings, 'talking_points_use_llm', False):
                tips: List[str] = []
                companies = [att.company for att in event.attendees if getattr(att, 'company', None)]
                if companies:
                    tips.append(f"Ask about current priorities at {companies[0]}")
                any_materials = any(getattr(att, 'materials', None) for att in event.attendees)
                if any_materials:
                    tips.append("Review shared materials before joining")
                if any(getattr(att, 'last_note_summary', None) for att in event.attendees):
                    tips.append("Skim last Affinity note for context")
                if tips:
                    tips = tips[: max(1, getattr(settings, 'talking_points_max', 2))]
                    line += "\n   \u2022 " + "\n   \u2022 ".join(tips)
            lines.append(line)

        return header + "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def generate_attendee_summary(self, attendee: AttendeeInfo) -> str:
        """Generate a summary for a specific attendee."""
        summary_parts = []

        summary_parts.append(f"{attendee.name}")
        if attendee.company:
            summary_parts.append(f"from {attendee.company}")
        if attendee.title:
            summary_parts.append(f"({attendee.title})")

        summary = " ".join(summary_parts)

        if attendee.recent_emails:
            summary += f"\nRecent context: {' '.join(attendee.recent_emails[:1])}"

        if attendee.news_articles:
            summary += f"\nRecent news: {len(attendee.news_articles)} articles found"
            for article in attendee.news_articles[:1]:
                summary += f"\n- {article.get('title', 'No title')}"

        return summary

    def generate_conversation_starters(self, attendee: AttendeeInfo) -> List[str]:
        """Generate conversation starters based on attendee information."""
        starters = []

        if attendee.company:
            starters.append(f"Ask about recent developments at {attendee.company}")
            starters.append(f"Discuss industry trends affecting {attendee.company}")

        if attendee.news_articles:
            latest_article = attendee.news_articles[0]
            starters.append(f"Discuss recent news: {latest_article.get('title', '')}")

        if attendee.title:
            starters.append(f"Ask about their role as {attendee.title}")

        starters.append("Ask about their current priorities and challenges")
        starters.append("Discuss potential collaboration opportunities")

        return starters[:3]

    # ------------------------------------------------------------------
    # Day structure / time block suggestions
    # ------------------------------------------------------------------

    def generate_time_blocks(
        self,
        events: List[MeetingEvent],
        news: List[Dict[str, Any]],
        todos: List[Dict[str, Any]],
        journal: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate suggested time blocks and research areas for the day.

        Combines journal context, today's meetings, pending to-dos, and AI
        news to produce 3-4 actionable time block suggestions.

        Returns a list of dicts with: title, description, block_type,
        suggested_duration_min, related_meeting, related_todo.
        """
        context = self._build_time_block_context(events, news, todos, journal)
        system = self._build_time_block_prompt()

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": context},
                ],
                response_format={"type": "json_object"},
                max_tokens=600,
                temperature=0.7,
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            blocks = data.get("time_blocks", [])

            result = []
            for b in blocks[:4]:
                if isinstance(b, dict) and b.get("title"):
                    result.append({
                        "title": b.get("title", ""),
                        "description": b.get("description", ""),
                        "block_type": b.get("block_type", "explore"),
                        "suggested_duration_min": b.get("suggested_duration_min"),
                        "related_meeting": b.get("related_meeting"),
                        "related_todo": b.get("related_todo"),
                    })
            return result

        except (json.JSONDecodeError, Exception) as e:
            print(f"[AI TimeBlocks] Error: {e}")
            return []

    def _build_time_block_prompt(self) -> str:
        """Build system prompt for time block generation."""
        owner_block = ""
        if owner_profile.name:
            owner_block = (
                f"You help {owner_profile.name}, "
                f"{owner_profile.title} at {owner_profile.company}, "
                f"structure their day.\n"
            )
            if owner_profile.focus:
                owner_block += f"Their focus areas: {owner_profile.focus}.\n"

        return (
            f"{owner_block}\n"
            "Based on their journal entry from last night, today's meetings, "
            "pending to-dos, and relevant AI/tech news, suggest 3-4 time blocks "
            "for the open windows in their day.\n\n"
            "Return a JSON object with exactly this structure:\n\n"
            "{\n"
            '  "time_blocks": [\n'
            "    {\n"
            '      "title": "Short, specific title",\n'
            '      "description": "Why this matters and what to do (1-2 sentences)",\n'
            '      "block_type": "research|follow-up|prep|explore",\n'
            '      "suggested_duration_min": 30,\n'
            '      "related_meeting": "Meeting title if connected, or null",\n'
            '      "related_todo": "Todo description if connected, or null"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "BLOCK TYPES:\n"
            "- research: Deep dives into topics from journal or news\n"
            "- follow-up: People or threads to close out\n"
            "- prep: Specific meeting preparation\n"
            "- explore: New areas from journal or news worth investigating\n\n"
            "RULES:\n"
            "- Be specific — reference actual meetings, people, and news items\n"
            "- Prioritize items from the journal entry (user's own priorities)\n"
            "- Suggest realistic durations (15-60 min)\n"
            "- If there's a journal entry, lead with what the user said matters\n"
            "- If no journal, focus on meeting prep and news-driven exploration\n"
            "- Return ONLY valid JSON, no markdown"
        )

    def _build_time_block_context(
        self,
        events: List[MeetingEvent],
        news: List[Dict[str, Any]],
        todos: List[Dict[str, Any]],
        journal: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build context string for time block generation."""
        parts = []

        # Journal context (highest priority)
        if journal:
            raw = journal.get("raw_text", "") if isinstance(journal, dict) else getattr(journal, "raw_text", "")
            if raw:
                parts.append(f"JOURNAL ENTRY (last night):\n{raw[:500]}")

            focus = journal.get("focus_areas", []) if isinstance(journal, dict) else getattr(journal, "focus_areas", [])
            if focus:
                parts.append(f"FOCUS AREAS: {', '.join(focus)}")

            reflections = journal.get("reflections", "") if isinstance(journal, dict) else getattr(journal, "reflections", "")
            if reflections:
                parts.append(f"REFLECTIONS: {reflections[:200]}")

        # Today's meetings
        if events:
            meeting_lines = []
            for ev in events:
                time_str = ev.start_time.strftime('%I:%M %p').lstrip('0')
                names = [att.name or att.email.split('@')[0] for att in ev.attendees[:3]]
                meeting_lines.append(f"  {time_str} — {ev.title} (with {', '.join(names)})")
            parts.append("TODAY'S MEETINGS:\n" + "\n".join(meeting_lines))

        # Pending to-dos
        if todos:
            todo_lines = []
            for t in todos[:8]:
                desc = t.get("description", "") if isinstance(t, dict) else getattr(t, "description", "")
                src = t.get("source", "") if isinstance(t, dict) else getattr(t, "source", "")
                todo_lines.append(f"  [{src}] {desc}")
            parts.append("PENDING TO-DOS:\n" + "\n".join(todo_lines))

        # AI news headlines
        if news:
            news_lines = []
            for n in news[:5]:
                title = n.get("title", "") if isinstance(n, dict) else ""
                tag = n.get("relevance_tag", "") if isinstance(n, dict) else ""
                news_lines.append(f"  [{tag}] {title}")
            parts.append("AI/TECH NEWS:\n" + "\n".join(news_lines))

        return "\n\n".join(parts) if parts else "No context available today."
