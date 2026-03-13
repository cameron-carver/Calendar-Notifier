import asyncio
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.brief import Brief, UserSettings
from app.schemas.brief import MeetingEvent, AttendeeInfo, BriefResponse
from app.services.calendar.google_calendar import GoogleCalendarService
from app.services.affinity.affinity_client import AffinityClient
from app.services.news.news_service import NewsService
from app.services.ai.summarization_service import SummarizationService
from app.services.email.gmail_service import GmailService
from app.services.persona.classifier import PersonaClassifier
from app.services.web.web_enrichment_service import WebEnrichmentService
from app.core.owner_profile import OwnerProfile
from app.core.utils.text import clean_calendar_description
import pytz
from app.core.config import settings
from app.core.network_db import get_network_session
from app.services.network_context_service import NetworkContextService
from app.services.network_sync_service import NetworkSyncService


class BriefService:
    """Main service for generating and sending morning briefs."""

    def __init__(self, executive_id: Optional[int] = None, db: Optional[Session] = None):
        """
        Initialize BriefService.

        Args:
            executive_id: If provided, generates briefs for this executive (EA mode)
                         If None, uses global settings (single-user mode)
            db: Database session for executive lookup
        """
        self.executive_id = executive_id
        self.db = db

        # Load executive profile and settings
        if executive_id and db:
            # EA mode - load from database
            from app.services.executive_service import ExecutiveService

            exec_service = ExecutiveService(db)
            executive = exec_service.get_executive(executive_id)

            if not executive:
                raise ValueError(f"Executive {executive_id} not found")

            if not executive.is_active:
                raise ValueError(f"Executive {executive_id} is inactive")

            # Build OwnerProfile from Executive model
            owner_profile = self._executive_to_owner_profile(executive)
            calendar_ids = executive.google_calendar_ids or []
            self.settings_resolver = self._create_settings_resolver(executive)
        else:
            # Single-user mode - use global singleton
            from app.core.owner_profile import owner_profile as global_profile
            owner_profile = global_profile

            calendar_ids = []
            if settings.google_calendar_ids:
                calendar_ids = [c.strip() for c in settings.google_calendar_ids.split(',') if c.strip()]

            self.settings_resolver = None  # Use global settings directly

        # Initialize services with executive context
        self.calendar_service = GoogleCalendarService(calendar_ids or ['primary'])
        self.affinity_client = AffinityClient()
        self.news_service = NewsService()
        self.summarization_service = SummarizationService()
        self.email_service = GmailService()
        self.persona_classifier = PersonaClassifier(owner_profile)
        self.web_enrichment_service = WebEnrichmentService()

        # Network Builder integration (shared database)
        self._network_db_session = get_network_session()
        self.network_context_service = NetworkContextService(self._network_db_session)
        self.network_sync_service = NetworkSyncService(self._network_db_session)

        # Resolve owner email for network interactions
        self._owner_email = (
            owner_profile.email if hasattr(owner_profile, 'email') else settings.owner_email
        )

    def _executive_to_owner_profile(self, executive) -> OwnerProfile:
        """Convert Executive model to OwnerProfile."""
        return OwnerProfile(
            name=executive.name,
            title=executive.title or "",
            company=settings.owner_company,  # Keep global for now
            focus=executive.focus_area or "",
            email=executive.email,
            linkedin=executive.linkedin_url or "",
        )

    def _create_settings_resolver(self, executive):
        """Create settings resolver for executive."""
        class ExecutiveSettings:
            def __init__(self, exec_model, global_settings):
                self.exec = exec_model
                self.global_settings = global_settings

            def get_feature_flag(self, flag_name: str) -> bool:
                """Get feature flag with executive override."""
                exec_value = getattr(self.exec, flag_name, None)
                if exec_value is not None:
                    return exec_value
                return getattr(self.global_settings, flag_name, False)

            def get_filter_setting(self, setting_name: str) -> Optional[bool]:
                """Get filter setting with executive override."""
                exec_value = getattr(self.exec, setting_name, None)
                if exec_value is not None:
                    return exec_value
                return getattr(self.global_settings, setting_name, None)

        return ExecutiveSettings(executive, settings)
    
    async def generate_daily_brief(self, target_date: Optional[date] = None) -> BriefResponse:
        """Generate a complete morning brief for the specified date.

        Orchestrates: calendar events + enrichment, AI news, journal context,
        weekly todos, per-meeting AI prep, and day structure time blocks.
        """
        if target_date is None:
            target_date = date.today()

        # Get calendar events
        events = self.calendar_service.get_daily_events(target_date)
        enriched_events: List[MeetingEvent] = []

        if events:
            # Enrich attendee information
            enriched_events = await self._enrich_events(events)
            # Add prior meeting history
            await self._enrich_with_history(enriched_events)

        # ── Parallel fetch: AI news + journal context (no interdependencies) ──
        news_task = self.web_enrichment_service.fetch_ai_news()
        journal_task = self._fetch_journal_context()
        industry_news, journal_ctx = await asyncio.gather(news_task, journal_task)

        # ── Weekly todos: DB queries (fast) + journal todos merged ──
        weekly_todos = self._gather_todos(journal_ctx)

        # ── Per-meeting AI prep (parallel across meetings) ──
        if enriched_events:
            await self._generate_ai_prep(enriched_events)

        # ── Day structure / time blocks (needs all context) ──
        time_blocks = []
        try:
            time_blocks = self.summarization_service.generate_time_blocks(
                enriched_events,
                industry_news,
                [t.model_dump(mode="json") if hasattr(t, "model_dump") else t for t in weekly_todos],
                journal_ctx.model_dump(mode="json") if journal_ctx else None,
            )
        except Exception as e:
            print(f"[Brief] Time block generation failed: {e}")

        # ── Generate brief content (plain text for text/plain MIME part) ──
        brief_content = (
            self.summarization_service.generate_meeting_brief(enriched_events)
            if enriched_events
            else f"No meetings scheduled for {target_date.strftime('%B %d, %Y')}."
        )

        # ── Convert raw dicts to schema objects for the response ──
        from app.schemas.brief import NewsArticle, TodoItem, TimeBlock, JournalContext

        news_articles = [NewsArticle(**a) for a in industry_news] if industry_news else []
        time_block_objs = [TimeBlock(**b) for b in time_blocks] if time_blocks else []

        # Create brief response
        brief_response = BriefResponse(
            id=0,
            date=datetime.combine(target_date, datetime.min.time()),
            content=brief_content,
            events_summary=enriched_events,
            created_at=datetime.now(),
            is_sent=False,
            industry_news=news_articles,
            weekly_todos=weekly_todos,
            time_blocks=time_block_objs,
            journal_context=journal_ctx,
        )

        return brief_response

    async def _fetch_journal_context(self):
        """Fetch and parse the latest journal reply (if any)."""
        try:
            if not self.db:
                from app.core.database import SessionLocal
                db = SessionLocal()
            else:
                db = self.db

            from app.services.journal_service import JournalService

            journal_service = JournalService(
                db=db,
                gmail=self.email_service,
                ai=self.summarization_service,
                executive_id=self.executive_id,
            )

            # Try to fetch a pending reply first
            ctx = await journal_service.fetch_and_parse_reply()
            if ctx:
                return ctx

            # Fall back to most recent parsed journal
            return journal_service.get_latest_journal_context()

        except Exception as e:
            print(f"[Brief] Journal context fetch failed: {e}")
            return None

    def _gather_todos(self, journal_ctx=None) -> list:
        """Merge todos from journal + DB sources."""
        from app.schemas.brief import TodoItem

        all_todos: list = []

        # 1. Journal todos (highest priority — user's own words)
        if journal_ctx:
            journal_todos = (
                journal_ctx.todos_extracted
                if hasattr(journal_ctx, "todos_extracted")
                else []
            )
            all_todos.extend(journal_todos)

        # 2. DB todos (annotations + relationship follow-ups)
        try:
            if self.db:
                from app.services.journal_service import JournalService

                journal_service = JournalService(
                    db=self.db,
                    gmail=self.email_service,
                    ai=self.summarization_service,
                    executive_id=self.executive_id,
                )
                db_todos = journal_service.get_weekly_todos()
                all_todos.extend(db_todos)
        except Exception as e:
            print(f"[Brief] DB todo fetch failed: {e}")

        return all_todos
    
    async def _enrich_events(self, events: List[MeetingEvent]) -> List[MeetingEvent]:
        """Enrich all events with attendee info, persona classification, and news.
        Recurring events are passed through without enrichment (lightweight).
        """
        enriched_events = []

        # Fetch annotations for executive (if EA mode)
        annotation_service = None
        if self.executive_id and self.db:
            from app.services.annotation_service import AnnotationService
            annotation_service = AnnotationService(self.db)

        for event in events:
            # Skip enrichment for recurring events — just pass through
            if event.is_recurring:
                enriched_events.append(event)
                continue

            # Fetch annotation for this meeting (EA mode)
            if annotation_service:
                annotation = annotation_service.get_annotation(
                    self.executive_id,
                    event.event_id
                )

                if annotation:
                    # Attach annotation to event
                    event.annotation = {
                        'priority': annotation.priority,
                        'prep_notes': annotation.prep_notes,
                        'action_before_meeting': annotation.action_before_meeting,
                    }

                    # Prepend prep notes to event description
                    if annotation.prep_notes:
                        prep_section = f"**EA Notes:** {annotation.prep_notes}\n\n"
                        event.description = prep_section + (event.description or '')

            # Enrich each attendee
            enriched_attendees = []
            for attendee in event.attendees:
                # Enrich with Affinity data
                enriched_attendee = await self.affinity_client.enrich_attendee_info(attendee)

                # Web enrichment fallback (fills gaps Affinity missed)
                enriched_attendee = await self.web_enrichment_service.enrich_attendee(enriched_attendee)

                # Classify persona (uses domain + title heuristics)
                persona = self.persona_classifier.classify(enriched_attendee)
                enriched_attendee.persona_type = persona.value

                # Company description from website (fills gap if Affinity/person lookup missed it)
                enriched_attendee = await self.web_enrichment_service.enrich_company_description(enriched_attendee)

                # Enrich with news (if news API is configured)
                if self.news_service.api_key:
                    attendee_dict = enriched_attendee.dict()
                    attendee_dict = await self.news_service.enrich_attendee_with_news(attendee_dict)
                    enriched_attendee = AttendeeInfo(**attendee_dict)

                enriched_attendees.append(enriched_attendee)

            # Clean event description (strip Zoom/Calendly boilerplate)
            cleaned_desc = clean_calendar_description(event.description) or event.description

            # Create enriched event (preserve all original fields)
            enriched_event = MeetingEvent(
                event_id=event.event_id,
                title=event.title,
                start_time=event.start_time,
                end_time=event.end_time,
                attendees=enriched_attendees,
                description=cleaned_desc,
                location=event.location,
                meeting_url=event.meeting_url,
                calendar_url=event.calendar_url,
                duration_minutes=event.duration_minutes,
                is_recurring=event.is_recurring,
            )

            enriched_events.append(enriched_event)

        return enriched_events

    async def _generate_ai_prep(self, events: List[MeetingEvent]) -> None:
        """Generate per-meeting AI prep and attach to each event."""
        if not events:
            return

        # Run all meetings in parallel for speed
        import asyncio

        async def _prep_one(event: MeetingEvent):
            try:
                result = self.summarization_service.generate_per_meeting_prep(event)
                if result:
                    event.ai_summary = result
            except Exception as e:
                print(f"[AI Prep] Failed for '{event.title}': {e}")

        await asyncio.gather(*[_prep_one(ev) for ev in events])

    async def _enrich_with_history(self, events: List[MeetingEvent]) -> None:
        """Annotate attendees with prior meeting history from Calendar.
        Mutates AttendeeInfo objects in-place.
        """
        if not events:
            return

        # Initialize relationship service (if EA mode)
        relationship_service = None
        if self.executive_id and self.db:
            from app.services.relationship_service import RelationshipService
            relationship_service = RelationshipService(self.db)

        # Collect unique attendee emails
        unique_emails = set()
        for ev in events:
            for att in ev.attendees:
                if att and att.email:
                    unique_emails.add(att.email.lower())

        if not unique_emails:
            return

        # Determine lookback window
        tz = pytz.timezone(settings.timezone)
        end_dt = datetime.now(tz)
        start_dt = end_dt - timedelta(days=getattr(settings, 'history_lookback_days', 120))

        # Fetch past events once
        past_events = self.calendar_service.get_events_for_date_range(start_dt, end_dt)

        # Build stats per email
        from collections import defaultdict
        email_to_count = defaultdict(int)
        email_to_last: dict[str, datetime] = {}
        email_to_titles: dict[str, list] = defaultdict(list)

        for pev in past_events:
            pev_title = getattr(pev, 'title', '') or ''
            for patt in getattr(pev, 'attendees', []) or []:
                email = (patt.email or '').lower()
                if not email or email not in unique_emails:
                    continue
                email_to_count[email] += 1
                st = getattr(pev, 'start_time', None)
                if isinstance(st, datetime):
                    last = email_to_last.get(email)
                    if (last is None) or (st > last):
                        email_to_last[email] = st
                    # Track titles sorted by time (most recent first)
                    if pev_title:
                        email_to_titles[email].append((st, pev_title))

        # Sort titles by date descending, keep last 3
        for email in email_to_titles:
            email_to_titles[email].sort(key=lambda x: x[0], reverse=True)
            email_to_titles[email] = [t for _, t in email_to_titles[email][:3]]

        # Apply to attendees and track relationships
        for ev in events:
            for att in ev.attendees:
                key = (att.email or '').lower()
                if not key:
                    continue
                if key in email_to_last:
                    att.last_meeting_date = email_to_last[key]
                if key in email_to_count:
                    att.meetings_past_n_days = email_to_count[key]
                if key in email_to_titles:
                    att.recent_meeting_titles = email_to_titles[key]

                # Track relationships in EA mode
                if relationship_service:
                    # Record this meeting occurrence
                    relationship_service.record_meeting(
                        executive_id=self.executive_id,
                        person_email=att.email,
                        meeting_date=ev.start_time,
                        person_name=att.name,
                        person_company=att.company
                    )

                    # Fetch relationship data for context
                    rel = relationship_service.get_relationship(
                        self.executive_id,
                        att.email
                    )

                    if rel:
                        # Add relationship context to attendee
                        att.relationship_strength = rel.relationship_strength
                        att.relationship_notes = rel.relationship_notes
                        att.personal_details = rel.personal_details

                # --- Network Builder enrichment ---
                if self.network_context_service.enabled and att.email:
                    # Get graph metrics for this attendee
                    nb_ctx = self.network_context_service.get_person_context(att.email)
                    if nb_ctx:
                        att.network_pagerank = nb_ctx.get("pagerank")
                        att.network_centrality = nb_ctx.get("degree_centrality")
                        att.network_cluster_id = nb_ctx.get("cluster_id")
                        att.network_total_connections = nb_ctx.get("total_connections")
                        att.network_strength_label = nb_ctx.get("network_strength_label")

                    # Get relationship-level context (exec ↔ attendee)
                    if self._owner_email:
                        rel_ctx = self.network_context_service.get_relationship_context(
                            self._owner_email, att.email
                        )
                        if rel_ctx:
                            att.network_decay_score = rel_ctx.get("computed_decay_score")

                    # Backfill person data into NB
                    self.network_sync_service.backfill_person_data(
                        person_email=att.email,
                        name=att.name,
                        company=att.company,
                        linkedin_url=att.linkedin_url,
                    )

            # --- Record meeting interactions in NB (event-level) ---
            if self.network_sync_service.enabled:
                attendee_emails = [
                    att.email for att in ev.attendees if att and att.email
                ]
                if self._owner_email and attendee_emails:
                    self.network_sync_service.record_meeting_interaction(
                        executive_email=self._owner_email,
                        attendee_emails=attendee_emails,
                        meeting_date=ev.start_time,
                        meeting_title=ev.title,
                    )
                    # Also record co-attendance edges between external attendees
                    if len(attendee_emails) > 1:
                        self.network_sync_service.record_co_attendance(
                            attendee_emails=attendee_emails,
                            meeting_date=ev.start_time,
                        )

        # Clean up NB database session when done
        if self._network_db_session:
            try:
                self._network_db_session.close()
            except Exception:
                pass

    async def send_morning_brief(
        self,
        user_email: str,
        brief_content: str,
        enriched_events: Optional[List[MeetingEvent]] = None,
        brief_response: Optional[BriefResponse] = None,
    ) -> bool:
        """Send the morning brief via email.

        If *brief_response* is provided, its newsletter sections (news,
        todos, time_blocks) are passed through to the HTML renderer.
        If *enriched_events* are provided they are reused for the HTML
        render (avoids a redundant re-enrichment and preserves ai_summary).
        """
        try:
            # Use already-enriched events when available
            if enriched_events is None:
                events = self.calendar_service.get_daily_events(date.today())
                enriched_events = await self._enrich_events(events) if events else []

            # Extract newsletter sections from BriefResponse
            industry_news = []
            weekly_todos = []
            time_blocks = []
            if brief_response:
                industry_news = brief_response.industry_news or []
                weekly_todos = brief_response.weekly_todos or []
                time_blocks = brief_response.time_blocks or []

            html_content = self.email_service.create_html_brief(
                brief_content,
                events=enriched_events,
                industry_news=industry_news,
                weekly_todos=weekly_todos,
                time_blocks=time_blocks,
            )

            # Send email
            subject = f"Morning Brief - {datetime.now().strftime('%B %d, %Y')}"
            success = self.email_service.send_morning_brief(
                to_email=user_email,
                subject=subject,
                content=brief_content,
                html_content=html_content,
            )

            return success

        except Exception as e:
            print(f"Error sending morning brief: {e}")
            return False
    
    async def generate_and_send_brief(self, user_email: str, target_date: Optional[date] = None) -> bool:
        """Generate and send a morning brief in one operation."""
        try:
            # Generate brief
            brief_response = await self.generate_daily_brief(target_date)
            
            # Send email
            success = await self.send_morning_brief(user_email, brief_response.content)
            
            return success
            
        except Exception as e:
            print(f"Error generating and sending brief: {e}")
            return False

    async def generate_and_send_if_upcoming(self, user_email: str, window_hours: int = 2) -> bool:
        """Send a brief only if there is an external meeting within the next window hours."""
        try:
            from datetime import timedelta
            target = date.today()
            brief = await self.generate_daily_brief(target)
            has_upcoming = any(True for e in brief.events_summary)
            if not has_upcoming:
                return False
            return await self.send_morning_brief(user_email, brief.content)
        except Exception as e:
            print(f"Error in generate_and_send_if_upcoming: {e}")
            return False
    
    def save_brief_to_database(self, brief_response: BriefResponse, db: Session) -> Brief:
        """Save the brief to the database."""
        brief = Brief(
            date=brief_response.date,
            content=brief_response.content,
            events_summary=[
                event.model_dump(mode='json')
                for event in brief_response.events_summary
            ],
            created_at=brief_response.created_at,
            is_sent=brief_response.is_sent,
            executive_id=self.executive_id  # Add executive context
        )

        db.add(brief)
        db.commit()
        db.refresh(brief)

        return brief
    
    def get_user_settings(self, db: Session) -> Optional[UserSettings]:
        """Get user settings from database."""
        return db.query(UserSettings).first()
    
    def update_user_settings(self, settings_data: dict, db: Session) -> UserSettings:
        """Update user settings."""
        settings = db.query(UserSettings).first()
        
        if settings:
            for key, value in settings_data.items():
                setattr(settings, key, value)
        else:
            settings = UserSettings(**settings_data)
            db.add(settings)
        
        db.commit()
        db.refresh(settings)
        
        return settings
    
    def get_brief_history(self, db: Session, limit: int = 10) -> List[Brief]:
        """Get recent brief history."""
        return db.query(Brief).order_by(Brief.created_at.desc()).limit(limit).all() 