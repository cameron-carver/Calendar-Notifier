"""Journal service — orchestrates the evening journal prompt / morning reply loop.

7pm: send_evening_prompt() → email with today's meeting recap
User replies with free-form text
8am: fetch_and_parse_reply() → extract todos, focus areas, reflections
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.owner_profile import owner_profile
from app.models.brief import JournalEntry, MeetingAnnotation, PersonRelationship
from app.schemas.brief import JournalContext, TodoItem, MeetingEvent
from app.services.email.gmail_service import GmailService
from app.services.ai.summarization_service import SummarizationService

import html as html_lib


class JournalService:
    """Orchestrates the evening journal prompt and morning reply parsing."""

    def __init__(
        self,
        db: Session,
        gmail: GmailService,
        ai: SummarizationService,
        executive_id: Optional[int] = None,
    ):
        self.db = db
        self.gmail = gmail
        self.ai = ai
        self.executive_id = executive_id

    # ------------------------------------------------------------------
    # Evening: send journal prompt
    # ------------------------------------------------------------------

    async def send_evening_prompt(
        self,
        recipient: str,
        today_events: Optional[List[MeetingEvent]] = None,
    ) -> JournalEntry:
        """Send the 7pm journal prompt and create a JournalEntry record."""
        today = date.today()

        # Build meeting recap HTML for the prompt email
        recap_html = self._build_meeting_recap(today_events or [])

        # Send the email
        result = self.gmail.send_journal_prompt(recipient, recap_html)

        # Create journal entry record
        entry = JournalEntry(
            date=today,
            prompt_message_id=result.get("message_id"),
            prompt_thread_id=result.get("thread_id"),
            prompt_sent_at=datetime.now(),
            executive_id=self.executive_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)

        print(f"[Journal] Prompt sent for {today}, thread={result.get('thread_id')}")
        return entry

    # ------------------------------------------------------------------
    # Morning: fetch reply and parse
    # ------------------------------------------------------------------

    async def fetch_and_parse_reply(self) -> Optional[JournalContext]:
        """Fetch the latest journal reply and parse it into structured context.

        Looks for the most recent JournalEntry that has a prompt but no response,
        checks Gmail for a reply, and if found, parses it with AI.
        """
        entry = self._get_pending_entry()
        if not entry:
            print("[Journal] No pending journal entry found")
            return None

        # Check Gmail for reply
        reply_text = self.gmail.get_journal_reply(
            entry.prompt_thread_id,
            entry.prompt_message_id,
        )

        if not reply_text:
            print("[Journal] No reply found yet")
            return None

        # Store raw reply
        entry.response_text = reply_text
        entry.response_received_at = datetime.now()

        # Parse with AI
        context = await self._parse_response(reply_text)

        # Store extracted data
        entry.extracted_todos = [t.model_dump(mode="json") for t in context.todos_extracted]
        entry.extracted_focus_areas = context.focus_areas
        entry.extracted_reflections = context.reflections

        self.db.commit()
        print(f"[Journal] Reply parsed: {len(context.todos_extracted)} todos, {len(context.focus_areas)} focus areas")

        return context

    def get_latest_journal_context(self) -> Optional[JournalContext]:
        """Get the most recent parsed journal context (for morning brief).

        Returns context from the most recent entry that has a response,
        looking back up to 3 days.
        """
        cutoff = date.today() - timedelta(days=3)

        entry = (
            self.db.query(JournalEntry)
            .filter(
                JournalEntry.date >= cutoff,
                JournalEntry.response_text.isnot(None),
            )
            .order_by(JournalEntry.date.desc())
            .first()
        )

        if not entry or not entry.response_text:
            return None

        # Reconstruct JournalContext from stored data
        todos = []
        for t in (entry.extracted_todos or []):
            try:
                todos.append(TodoItem(**t))
            except Exception:
                pass

        return JournalContext(
            raw_text=entry.response_text,
            todos_extracted=todos,
            focus_areas=entry.extracted_focus_areas or [],
            reflections=entry.extracted_reflections,
            received_at=entry.response_received_at,
        )

    # ------------------------------------------------------------------
    # Weekly to-dos from DB
    # ------------------------------------------------------------------

    def get_weekly_todos(self) -> List[TodoItem]:
        """Aggregate to-dos from meeting annotations and relationship follow-ups.

        Pulls:
        1. MeetingAnnotation action_items with follow_up_required
        2. PersonRelationship next_follow_up within this week
        """
        todos: List[TodoItem] = []
        today = date.today()
        week_end = today + timedelta(days=(6 - today.weekday()))  # Sunday

        # 1. Meeting annotation action items
        annotations = (
            self.db.query(MeetingAnnotation)
            .filter(
                MeetingAnnotation.follow_up_required.is_(True),
                MeetingAnnotation.follow_up_date.isnot(None),
                MeetingAnnotation.follow_up_date <= datetime.combine(week_end, datetime.max.time()),
            )
            .order_by(MeetingAnnotation.follow_up_date.asc())
            .limit(10)
            .all()
        )

        for ann in annotations:
            # Extract action items from JSON
            for item in (ann.action_items or []):
                desc = item if isinstance(item, str) else item.get("description", str(item))
                todos.append(TodoItem(
                    description=desc,
                    source="action-item",
                    priority="high" if ann.priority in ("critical", "high") else "normal",
                    due_date=ann.follow_up_date,
                ))
            # If no action items but follow-up required, add the follow-up note
            if not ann.action_items and ann.follow_up_notes:
                todos.append(TodoItem(
                    description=ann.follow_up_notes,
                    source="action-item",
                    priority="normal",
                    due_date=ann.follow_up_date,
                ))

        # 2. Relationship follow-ups due this week
        relationships = (
            self.db.query(PersonRelationship)
            .filter(
                PersonRelationship.next_follow_up.isnot(None),
                PersonRelationship.next_follow_up <= datetime.combine(week_end, datetime.max.time()),
            )
            .order_by(PersonRelationship.next_follow_up.asc())
            .limit(10)
            .all()
        )

        for rel in relationships:
            name = rel.person_name or rel.person_email
            company = rel.person_company or ""
            todos.append(TodoItem(
                description=f"Follow up with {name}",
                source="follow-up",
                priority="normal",
                due_date=rel.next_follow_up,
                person_name=rel.person_name,
                person_company=company,
            ))

        return todos

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_pending_entry(self) -> Optional[JournalEntry]:
        """Get the most recent journal entry awaiting a reply."""
        cutoff = date.today() - timedelta(days=2)

        return (
            self.db.query(JournalEntry)
            .filter(
                JournalEntry.date >= cutoff,
                JournalEntry.prompt_thread_id.isnot(None),
                JournalEntry.response_text.is_(None),
            )
            .order_by(JournalEntry.date.desc())
            .first()
        )

    async def _parse_response(self, raw_text: str) -> JournalContext:
        """Use GPT-4o-mini to extract structured data from journal reply."""
        system_prompt = (
            f"You are parsing a free-form evening journal entry from {owner_profile.name or 'the user'}, "
            f"{owner_profile.title or 'a professional'} at {owner_profile.company or 'their company'}.\n\n"
            "Extract structured data from their reply. Return ONLY valid JSON:\n\n"
            "{\n"
            '  "todos": [\n'
            '    {"description": "...", "priority": "high|normal|low"}\n'
            "  ],\n"
            '  "focus_areas": ["area 1", "area 2"],\n'
            '  "reflections": "general thoughts or context that don\'t fit into todos or focus areas"\n'
            "}\n\n"
            "RULES:\n"
            "- todos: actionable items the user wants to do (tasks, follow-ups, things to remember)\n"
            "- focus_areas: topics or themes they want to explore, research, or think about\n"
            "- reflections: anything else — observations, context, thoughts\n"
            "- Be generous with classification — if something could be a todo, make it one\n"
            "- Keep descriptions concise but complete\n"
            "- Return ONLY valid JSON, no markdown"
        )

        try:
            response = self.ai.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Journal entry:\n\n{raw_text}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=600,
                temperature=0.3,
            )

            data = json.loads(response.choices[0].message.content or "{}")

            todos = []
            for t in data.get("todos", []):
                if isinstance(t, dict) and t.get("description"):
                    todos.append(TodoItem(
                        description=t["description"],
                        source="journal",
                        priority=t.get("priority", "normal"),
                    ))

            return JournalContext(
                raw_text=raw_text,
                todos_extracted=todos,
                focus_areas=data.get("focus_areas", []),
                reflections=data.get("reflections"),
                received_at=datetime.now(),
            )

        except Exception as e:
            print(f"[Journal] Error parsing response with AI: {e}")
            # Fallback: return raw text as single reflection
            return JournalContext(
                raw_text=raw_text,
                reflections=raw_text,
                received_at=datetime.now(),
            )

    @staticmethod
    def _build_meeting_recap(events: List[MeetingEvent]) -> str:
        """Build a compact HTML recap of today's meetings for the journal prompt."""
        if not events:
            return '<div style="color: #6b7280; font-size: 13px;">No meetings today.</div>'

        items = []
        for ev in events:
            time_str = ev.start_time.strftime('%I:%M %p').lstrip('0')
            names = []
            for att in ev.attendees[:4]:
                name = (att.name or att.email.split('@')[0]).split()[0]
                names.append(html_lib.escape(name))
            people = ", ".join(names)
            extra = len(ev.attendees) - len(names)
            if extra > 0:
                people += f" +{extra}"

            items.append(
                f'<div style="padding: 6px 0; font-size: 13px; color: #374151;">'
                f'<span style="color: #6b4f1d; font-weight: 600;">{html_lib.escape(time_str)}</span> '
                f'{html_lib.escape(ev.title or "Meeting")} '
                f'<span style="color: #6b7280;">with {people}</span>'
                f'</div>'
            )

        return '\n'.join(items)
