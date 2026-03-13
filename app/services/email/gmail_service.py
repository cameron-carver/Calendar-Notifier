import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import html as html_lib
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Optional, List
from app.core.config import settings
from app.core.owner_profile import owner_profile
from app.services.persona.classifier import PersonaType
from app.schemas.brief import MeetingEvent, AttendeeInfo
from dateutil import parser as dateutil_parser
import urllib.parse as urlparse
from app.core.utils.text import clean_calendar_description


class GmailService:
    """Service for sending emails via Gmail API."""
    
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.readonly',
    ]
    
    def __init__(self) -> None:
        self.service = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Gmail API."""
        creds = None
        
        # Load credentials from file
        if os.path.exists(settings.gmail_credentials_file):
            creds = Credentials.from_authorized_user_file(
                settings.gmail_credentials_file, 
                self.SCOPES
            )
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # This would typically be done during setup
                # For now, we'll assume credentials are already set up
                raise Exception("Gmail credentials not found. Please set up OAuth2 credentials.")
            
            # Save the credentials for the next run
            with open(settings.gmail_credentials_file, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('gmail', 'v1', credentials=creds)
    
    def send_morning_brief(self, to_email: str, subject: str, content: str, html_content: Optional[str] = None) -> bool:
        """Send a morning brief email."""
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['to'] = to_email
            message['subject'] = subject
            
            # Add text content
            text_part = MIMEText(content, 'plain')
            message.attach(text_part)
            
            # Add HTML content if provided
            if html_content:
                html_part = MIMEText(html_content, 'html')
                message.attach(html_part)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send email
            self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            return True
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return False
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
    
    def create_html_brief(
        self,
        content: str,
        events: Optional[List[MeetingEvent]] = None,
        industry_news: Optional[List] = None,
        weekly_todos: Optional[List] = None,
        time_blocks: Optional[List] = None,
    ) -> str:
        """Render a clean, newsletter-style HTML from the concise text brief.

        If `events` are provided, use structured data (including LinkedIn links,
        AI prep, relationship signals, etc.) instead of regex parsing.
        New newsletter sections: time_blocks, industry_news, weekly_todos.
        """
        from datetime import datetime as _dt

        lines = [ln.strip() for ln in content.splitlines()]
        items = []

        def normalize_name(raw: str) -> str:
            if not raw:
                return ""
            first = raw.strip().split()[0]
            return first[:1].upper() + first[1:]

        # ── Helper: relationship signal ──
        def _relationship_signal(ev_attendees) -> str:
            """Return a coloured dot + label based on meeting history.
            🟢 First meeting  🔵 Active (met ≤30 days)  🟡 Reconnecting (met >30 days)
            """
            best_date = None
            for att in ev_attendees:
                dt = getattr(att, 'last_meeting_date', None)
                if dt is None:
                    continue
                if isinstance(dt, str):
                    try:
                        from dateutil import parser as _p
                        dt = _p.isoparse(dt)
                    except Exception:
                        continue
                if best_date is None or dt > best_date:
                    best_date = dt
            if best_date is None:
                return '<span class="rel-signal rel-first">&#x1F7E2; First meeting</span>'
            from datetime import datetime as _ddt, timezone as _tz
            if best_date.tzinfo is None:
                days_ago = (_ddt.now() - best_date).days
            else:
                days_ago = (_ddt.now(_tz.utc) - best_date).days
            if days_ago <= 30:
                return '<span class="rel-signal rel-active">&#x1F535; Active</span>'
            return '<span class="rel-signal rel-reconnect">&#x1F7E1; Reconnecting</span>'

        # ── Helper: meeting format label ──
        def _format_label(count: int) -> str:
            if count <= 2:
                return "1:1"
            return "Group"

        # ── Build structured items from events ──
        summary_html = ""
        if events:
            # Build top summary chips
            try:
                total_meetings = len(events)
                first_start = min(ev.start_time for ev in events)
                last_end = max(ev.end_time for ev in events)
                unique_people = set()
                unique_companies = set()
                for ev in events:
                    for att in ev.attendees:
                        if getattr(att, 'email', None):
                            unique_people.add(att.email.lower())
                        comp = getattr(att, 'company', None)
                        if comp:
                            unique_companies.add(comp.strip().lower())
                def fmt_time(dt):
                    return f"{dt.strftime('%I:%M %p').lstrip('0')}"
                chips = [
                    f'<span class="chip-info">{total_meetings} meeting{"s" if total_meetings != 1 else ""}</span>',
                    f'<span class="chip-info">First at {fmt_time(first_start)}</span>',
                    f'<span class="chip-info">Window {fmt_time(first_start)}\u2013{fmt_time(last_end)}</span>',
                    f'<span class="chip-info">People {len(unique_people)}</span>',
                ]
                if unique_companies:
                    chips.append(f'<span class="chip-info">Companies {len(unique_companies)}</span>')
                summary_html = '<div class="summary">' + ''.join(chips) + '</div>'
            except Exception:
                summary_html = ""

            for ev in events:
                time_range = f"{ev.start_time.strftime('%I:%M %p').lstrip('0')}\u2013{ev.end_time.strftime('%I:%M %p').lstrip('0')}"
                attendees_html_parts = []
                people_details = []
                for att in ev.attendees[:8]:
                    name = normalize_name(att.name or att.email.split('@')[0])
                    linkedin = getattr(att, 'linkedin_url', None)
                    if not linkedin:
                        full_name = (att.name or att.email.split('@')[0]).strip()
                        company = getattr(att, 'company', None)
                        parts = [full_name]
                        if company:
                            parts.append(company)
                        parts.append('linkedin')
                        q = ' '.join(parts)
                        linkedin = f"https://www.google.com/search?q={urlparse.quote_plus(q)}"
                    attendees_html_parts.append(
                        '<a href="' + linkedin + '" target="_blank" rel="noopener noreferrer">'
                        + html_lib.escape(name) + '<span class="li-icon">\u2197</span></a>'
                    )
                    # Persona badge
                    persona_chip = ""
                    persona_val = getattr(att, 'persona_type', None) or ""
                    if persona_val and persona_val not in ("unknown", "internal"):
                        try:
                            pt = PersonaType(persona_val)
                            persona_chip = (
                                f'<span class="persona-badge" style="background:{pt.color};color:{pt.text_color};">'
                                f'{html_lib.escape(pt.label)}</span>'
                            )
                        except ValueError:
                            pass
                    # People meta line
                    meta_bits = []
                    att_title = getattr(att, 'title', None)
                    att_company = getattr(att, 'company', None)
                    if att_title:
                        meta_bits.append(html_lib.escape(att_title))
                    if att_company:
                        meta_bits.append(html_lib.escape(att_company))
                    meta = " , ".join(meta_bits)
                    if meta or persona_chip:
                        meta_str = f' <span class="meta">\u2014 {meta}</span>' if meta else ""
                        people_details.append(
                            f'<li><span class="name">{html_lib.escape(name)}</span>'
                            f'{persona_chip}{meta_str}</li>'
                        )
                attendees_joined = ", ".join(attendees_html_parts)

                # Company info (website, description) from attendees
                company_website = None
                company_desc = None
                for att in ev.attendees:
                    if not company_website and getattr(att, 'website_url', None):
                        company_website = att.website_url
                    if not company_desc and getattr(att, 'company_description', None):
                        company_desc = att.company_description
                    if company_website and company_desc:
                        break

                about_text = ""
                if company_website:
                    about_text = (
                        f'<a href="{html_lib.escape(company_website)}" target="_blank" '
                        f'rel="noopener noreferrer">{html_lib.escape(company_website)}</a>'
                    )
                    if company_desc:
                        desc_short = (company_desc[:100] + "\u2026") if len(company_desc) > 100 else company_desc
                        about_text += f" \u2014 {html_lib.escape(desc_short)}"
                elif company_desc:
                    desc_short = (company_desc[:120] + "\u2026") if len(company_desc) > 120 else company_desc
                    about_text = html_lib.escape(desc_short)
                else:
                    for att in ev.attendees:
                        if getattr(att, 'last_note_summary', None):
                            about_text = att.last_note_summary
                            break
                    if not about_text and ev.description:
                        # Clean boilerplate before using as About fallback
                        cleaned = clean_calendar_description(ev.description)
                        if cleaned:
                            about_text = re.sub(r"<[^>]+>", " ", html_lib.unescape(cleaned))
                    if about_text:
                        about_text = (about_text[:120] + "\u2026") if len(about_text) > 120 else about_text
                        about_text = html_lib.escape(about_text)
                    else:
                        about_text = ""

                # Context date from Affinity last note
                context_text = ""
                for att in ev.attendees:
                    if getattr(att, 'last_note_date', None):
                        try:
                            dt = dateutil_parser.isoparse(att.last_note_date)
                            context_text = f"Context: last note on {dt.strftime('%b %d, %Y')}"
                        except Exception:
                            context_text = f"Context: last note on {html_lib.escape(att.last_note_date[:10])}"
                        break

                # Meeting size chip + format label
                count = len(ev.attendees)
                if count >= 8:
                    chip_class = 'chip-large'
                elif count >= 4:
                    chip_class = 'chip-medium'
                else:
                    chip_class = 'chip-small'
                format_lbl = _format_label(count)
                chip_html = (
                    f'<span class="chip {chip_class}">{format_lbl} \u00b7 '
                    f'{count} attendee{"s" if count != 1 else ""}</span>'
                )

                # Duration chip
                dur_chip = ""
                dur = getattr(ev, 'duration_minutes', None)
                if dur:
                    dur_chip = f'<span class="chip chip-duration">{dur} min</span>'

                # Join button
                join_html = ""
                meeting_url = getattr(ev, 'meeting_url', None)
                if meeting_url:
                    join_html = (
                        f'<a href="{html_lib.escape(meeting_url)}" target="_blank" '
                        f'rel="noopener noreferrer" class="join-btn">Join \u2192</a>'
                    )

                # Relationship signal
                rel_signal = _relationship_signal(ev.attendees)

                # Materials (Affinity)
                materials_urls = []
                for att in ev.attendees:
                    for u in (getattr(att, 'materials', None) or []):
                        if u not in materials_urls:
                            materials_urls.append(u)
                materials_urls = materials_urls[:3]

                # History text
                history_text = ""
                last_dates = []
                total_counts = []
                for att in ev.attendees:
                    if getattr(att, 'last_meeting_date', None):
                        try:
                            dt = att.last_meeting_date
                            from dateutil import parser as _p
                            if isinstance(dt, str):
                                dt = _p.isoparse(dt)
                            last_dates.append(dt)
                        except Exception:
                            pass
                    if getattr(att, 'meetings_past_n_days', None):
                        total_counts.append(att.meetings_past_n_days)
                if last_dates or total_counts:
                    last_dt = max(last_dates) if last_dates else None
                    last_txt = last_dt.strftime('%b %d, %Y') if last_dt else None
                    count_txt = max(total_counts) if total_counts else None
                    parts_ht = []
                    if last_txt:
                        parts_ht.append(f"last met on {last_txt}")
                    if count_txt:
                        parts_ht.append(f"{count_txt}x in last {getattr(settings, 'history_lookback_days', 120)} days")
                    if parts_ht:
                        history_text = "History: " + ", ".join(parts_ht)

                # AI prep block
                ai_prep = getattr(ev, 'ai_summary', None) or {}

                items.append({
                    "time": html_lib.escape(time_range),
                    "title": html_lib.escape(ev.title or "Untitled Meeting"),
                    "attendees_html": attendees_joined,
                    "about": about_text,
                    "context": html_lib.escape(context_text) if context_text else "",
                    "size_chip": chip_html,
                    "dur_chip": dur_chip,
                    "join_html": join_html,
                    "rel_signal": rel_signal,
                    "materials": materials_urls,
                    "people_details": people_details,
                    "history": html_lib.escape(history_text) if history_text else "",
                    "ai_prep": ai_prep,
                })
        else:
            # Fallback regex parse for plain-text briefs
            pattern = re.compile(
                r"^\U0001f4c5\s*(\d{1,2}:\d{2}\s*[AP]M\u2013\d{1,2}:\d{2}\s*[AP]M)\s+(.*?)(?:\s+\u2014\s+(.*?))?(?:\s+\u2014 About:\s+(.*))?$"
            )
            for ln in lines:
                if not ln.startswith("\U0001f4c5 "):
                    continue
                m = pattern.match(ln)
                if not m:
                    items.append({"time": "", "title": html_lib.escape(ln.replace('\U0001f4c5', '').strip()),
                                  "attendees_html": "", "about": "", "ai_prep": {}})
                    continue
                time_range, title_txt, attendees_txt, about_txt = m.groups()
                items.append({
                    "time": html_lib.escape(time_range or ""),
                    "title": html_lib.escape(title_txt or ""),
                    "attendees_html": html_lib.escape(attendees_txt or ""),
                    "about": html_lib.escape((about_txt or "").rstrip(".")),
                    "ai_prep": {},
                })

        # ── Build newsletter HTML per item ──
        items_html = []
        for it in items:
            attendees_html = (
                f'<span class="attendees">\u2014 {it["attendees_html"]}</span>'
                if it.get("attendees_html") else ""
            )
            about_html = f'<div class="about">About: {it["about"]}</div>' if it.get("about") else ""
            context_html = f'<div class="about">{it["context"]}</div>' if it.get("context") else ""
            history_html = f'<div class="about">{it["history"]}</div>' if it.get("history") else ""

            # Materials
            materials_html = ""
            if it.get('materials'):
                links = [
                    f'<a href="{html_lib.escape(u)}" target="_blank" rel="noopener noreferrer">\U0001f517</a>'
                    for u in it['materials']
                ]
                materials_html = f'<div class="materials"><span class="label">Materials:</span> {" ".join(links)}</div>'

            # People detail list
            people_html = ""
            if it.get('people_details'):
                people_html = '<ul class="people">' + "".join(it['people_details']) + "</ul>"

            # AI prep block
            ai_prep_html = ""
            ai = it.get("ai_prep") or {}
            if ai.get("purpose"):
                purpose_esc = html_lib.escape(ai["purpose"])
                actions_li = ""
                for act in (ai.get("prep_actions") or []):
                    actions_li += f"<li>{html_lib.escape(act)}</li>"
                kq_html = ""
                if ai.get("key_question"):
                    kq_esc = html_lib.escape(ai["key_question"])
                    kq_html = f'<div class="ai-kq">\U0001f4ac <em>{kq_esc}</em></div>'
                ai_prep_html = (
                    f'<div class="ai-prep">'
                    f'<div class="ai-purpose">{purpose_esc}</div>'
                    f'{f"<ul class=ai-actions>{actions_li}</ul>" if actions_li else ""}'
                    f'{kq_html}'
                    f'</div>'
                )

            # Chips row (join + duration + size + relationship)
            chips_row_parts = []
            if it.get('join_html'):
                chips_row_parts.append(it['join_html'])
            if it.get('dur_chip'):
                chips_row_parts.append(it['dur_chip'])
            if it.get('size_chip'):
                chips_row_parts.append(it['size_chip'])
            if it.get('rel_signal'):
                chips_row_parts.append(it['rel_signal'])
            chips_row = f'<div class="chips-row">{" ".join(chips_row_parts)}</div>' if chips_row_parts else ""

            items_html.append(
                f"""
                <li class="item">
                    <div class="row">
                        <div class="col time-col"><span class="time">{it['time']}</span></div>
                        <div class="col content-col">
                            <div class="title-line"><span class="title">{it['title']}</span></div>
                            {chips_row}
                            {attendees_html}
                            {people_html}
                            {about_html}
                            {context_html}
                            {history_html}
                            {materials_html}
                            {ai_prep_html}
                        </div>
                    </div>
                </li>
                """
            )

        now_ts = _dt.now().strftime('%B %d, %Y at %I:%M %p').replace(' 0', ' ')

        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                :root {{
                    --bg: #ffffff;
                    --text: #1f2937;
                    --muted: #6b7280;
                    --line: #e9ecef;
                    --accent: {html_lib.escape(settings.theme_accent)};
                    --accent2: {html_lib.escape(settings.theme_accent2)};
                    --chip-bg: #fff7e6;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: var(--text);
                    max-width: 720px;
                    margin: 0 auto;
                    padding: 28px 20px;
                    background: var(--bg);
                }}
                .header {{ margin-bottom: 16px; }}
                .header h1 {{ margin: 0 0 6px 0; font-size: 24px; letter-spacing: 0.2px; }}
                .header p {{ margin: 0; color: var(--muted); font-size: 13px; }}
                .summary {{ display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
                .chip-info {{
                    background: #f3f4f6; color: #374151; font-size: 12px;
                    padding: 4px 10px; border-radius: 999px; border: 1px solid #e5e7eb;
                }}
                ul.list {{ list-style: none; padding: 0; margin: 0; }}
                .item {{ padding: 16px 0; border-top: 1px solid var(--line); }}
                .item:first-child {{ border-top: 0; }}
                .row {{ display: table; width: 100%; }}
                .col {{ display: table-cell; vertical-align: top; }}
                .time-col {{ width: 140px; }}
                .content-col {{ width: auto; }}
                .time {{
                    color: #6b4f1d; font-weight: 600; font-size: 12px;
                    background: var(--chip-bg); border: 1px solid rgba(214,163,92,0.35);
                    padding: 4px 8px; border-radius: 999px;
                }}
                .title {{ font-weight: 700; font-size: 15px; }}
                .chips-row {{ display: flex; gap: 6px; align-items: center; margin-top: 6px; flex-wrap: wrap; }}
                .chip {{
                    font-size: 11px; padding: 2px 8px; border-radius: 999px;
                    border: 1px solid transparent; white-space: nowrap;
                }}
                .chip-small {{ background: #f5f3ff; color: #4c1d95; border-color: rgba(79,70,229,0.25); }}
                .chip-medium {{ background: #fff7e6; color: #6b4f1d; border-color: rgba(214,163,92,0.35); }}
                .chip-large {{ background: #fde2e2; color: #7f1d1d; border-color: rgba(185,28,28,0.25); }}
                .chip-duration {{ background: #f0f9ff; color: #075985; border-color: rgba(14,165,233,0.25); }}
                .join-btn {{
                    display: inline-block; font-size: 11px; font-weight: 600;
                    padding: 3px 10px; border-radius: 999px;
                    background: var(--accent); color: #fff; text-decoration: none;
                    letter-spacing: 0.2px;
                }}
                .join-btn:hover {{ opacity: 0.9; }}
                .rel-signal {{ font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #f9fafb; border: 1px solid #e5e7eb; white-space: nowrap; }}
                .attendees {{ color: #374151; margin-left: 8px; font-size: 13px; }}
                .li-icon {{ font-size: 11px; margin-left: 2px; color: #6b7280; }}
                .about {{ color: var(--muted); font-size: 12.5px; margin-top: 6px; }}
                .people {{ margin: 6px 0 0 0; padding-left: 18px; color: #4b5563; font-size: 12.5px; }}
                .people .name {{ font-weight: 600; color: #374151; }}
                .people .meta {{ color: #6b7280; }}
                .materials {{ margin-top: 4px; font-size: 12px; color: var(--muted); }}
                .materials a {{ color: var(--accent); text-decoration: none; }}
                .materials .label {{ margin-right: 6px; }}
                .persona-badge {{
                    font-size: 10px; font-weight: 600; padding: 2px 6px;
                    border-radius: 999px; margin-left: 4px;
                    vertical-align: middle; letter-spacing: 0.3px;
                }}
                /* AI Prep block */
                .ai-prep {{
                    margin-top: 10px; padding: 10px 14px;
                    background: #fffbf0; border-left: 3px solid var(--accent);
                    border-radius: 0 8px 8px 0; font-size: 12.5px;
                }}
                .ai-purpose {{ font-weight: 600; color: #374151; margin-bottom: 4px; }}
                .ai-actions {{ margin: 4px 0 4px 16px; padding: 0; color: #4b5563; }}
                .ai-actions li {{ margin-bottom: 2px; }}
                .ai-kq {{ margin-top: 6px; color: #92400e; font-size: 12px; }}
                /* Newsletter sections */
                .section {{ margin: 20px 0; }}
                .section-header {{
                    font-size: 14px; font-weight: 700; color: #1f2937;
                    margin-bottom: 10px; display: flex; align-items: center; gap: 8px;
                }}
                .section-icon {{ font-size: 16px; }}
                /* Time blocks */
                .time-block {{
                    padding: 10px 14px; margin-bottom: 8px;
                    background: #f0f9ff; border-left: 3px solid #0ea5e9;
                    border-radius: 0 8px 8px 0; font-size: 12.5px;
                }}
                .time-block .tb-title {{ font-weight: 600; color: #0c4a6e; margin-bottom: 2px; }}
                .time-block .tb-desc {{ color: #374151; }}
                .time-block .tb-meta {{ font-size: 11px; color: #6b7280; margin-top: 4px; }}
                .tb-type {{
                    font-size: 10px; font-weight: 600; padding: 2px 6px;
                    border-radius: 999px; margin-right: 6px;
                }}
                .tb-research {{ background: #ede9fe; color: #5b21b6; }}
                .tb-follow-up {{ background: #fef3c7; color: #92400e; }}
                .tb-prep {{ background: #d1fae5; color: #065f46; }}
                .tb-explore {{ background: #e0e7ff; color: #3730a3; }}
                /* News */
                .news-item {{
                    padding: 8px 0; border-bottom: 1px solid #f3f4f6;
                    font-size: 12.5px;
                }}
                .news-item:last-child {{ border-bottom: none; }}
                .news-title {{ font-weight: 600; color: #1f2937; }}
                .news-title a {{ color: #1f2937; text-decoration: none; }}
                .news-title a:hover {{ color: var(--accent); }}
                .news-source {{
                    font-size: 10px; font-weight: 600; padding: 2px 6px;
                    border-radius: 999px; background: #f3f4f6; color: #6b7280;
                    margin-left: 6px;
                }}
                .news-tag {{
                    font-size: 10px; padding: 1px 5px; border-radius: 999px;
                    background: #ede9fe; color: #5b21b6; margin-left: 4px;
                }}
                .news-summary {{ color: #6b7280; font-size: 11.5px; margin-top: 2px; }}
                /* Todos */
                .todo-item {{
                    padding: 6px 0; font-size: 12.5px; display: flex;
                    align-items: flex-start; gap: 8px;
                }}
                .todo-check {{ color: #d1d5db; font-size: 14px; flex-shrink: 0; }}
                .todo-desc {{ color: #374151; }}
                .todo-source {{
                    font-size: 10px; font-weight: 600; padding: 1px 5px;
                    border-radius: 999px; margin-left: 4px;
                }}
                .todo-journal {{ background: #dbeafe; color: #1e40af; }}
                .todo-followup {{ background: #fef3c7; color: #92400e; }}
                .todo-action {{ background: #d1fae5; color: #065f46; }}
                .todo-person {{ color: #6b7280; font-size: 11px; }}
                .footer {{
                    margin-top: 22px; padding-top: 12px;
                    border-top: 1px solid var(--line);
                    color: var(--muted); font-size: 11px;
                }}
                @media (max-width: 480px) {{
                    .time-col {{ width: 110px; }}
                    .title {{ font-size: 13.5px; }}
                    .attendees {{ font-size: 12.5px; }}
                    .chips-row {{ gap: 4px; }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div style="background: linear-gradient(90deg, var(--accent), var(--accent2)); color: white; padding: 22px; border-radius: 14px; display: flex; align-items: center; gap: 14px;">
                    <div style="font-size: 28px;">\U0001f9ac</div>
                    <div>
                        <div style="font-size: 24px; font-weight: 800; letter-spacing: 0.2px;">{html_lib.escape(owner_profile.short_name + "'s" if owner_profile.short_name else "Blackhorn")} Morning Brief</div>
                        <div style="opacity: 0.95; font-size: 13px;">{html_lib.escape(owner_profile.summary_line()) if owner_profile.name else "Your daily meeting preparation summary"}</div>
                    </div>
                </div>
                {summary_html if events else ''}
            </div>
            {self._render_time_blocks(time_blocks)}
            {self._render_news_section(industry_news)}
            {self._render_todos_section(weekly_todos)}
            {'<div class="section-header" style="margin-top: 20px;"><span class="section-icon">&#x1F4C5;</span> Today&#x27;s Meetings</div>' if items_html else ''}
            <ul class="list">
                {''.join(items_html)}
            </ul>
            <div class="footer">Generated by Morning Brief \u00b7 {html_lib.escape(now_ts)}</div>
        </body>
        </html>
        """
        return html_template
    
    # ------------------------------------------------------------------
    # Newsletter section renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_time_blocks(time_blocks: Optional[List] = None) -> str:
        """Render the 'Your Day' time blocks section."""
        if not time_blocks:
            return ""

        blocks_html = []
        for b in time_blocks:
            # Support both dict and Pydantic model
            title = b.get("title", "") if isinstance(b, dict) else getattr(b, "title", "")
            desc = b.get("description", "") if isinstance(b, dict) else getattr(b, "description", "")
            btype = b.get("block_type", "explore") if isinstance(b, dict) else getattr(b, "block_type", "explore")
            duration = b.get("suggested_duration_min") if isinstance(b, dict) else getattr(b, "suggested_duration_min", None)

            type_class = f"tb-{btype}" if btype in ("research", "follow-up", "prep", "explore") else "tb-explore"
            type_label = btype.replace("-", " ").title()

            meta_parts = []
            if duration:
                meta_parts.append(f"{duration} min")
            meta_html = f'<div class="tb-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""

            blocks_html.append(
                f'<div class="time-block">'
                f'<span class="tb-type {html_lib.escape(type_class)}">{html_lib.escape(type_label)}</span>'
                f'<span class="tb-title">{html_lib.escape(title)}</span>'
                f'<div class="tb-desc">{html_lib.escape(desc)}</div>'
                f'{meta_html}'
                f'</div>'
            )

        return (
            f'<div class="section">'
            f'<div class="section-header"><span class="section-icon">&#x1F4CB;</span> Your Day</div>'
            f'{"".join(blocks_html)}'
            f'</div>'
        )

    @staticmethod
    def _render_news_section(news: Optional[List] = None) -> str:
        """Render the 'AI Pulse' news section."""
        if not news:
            return ""

        items_html = []
        for n in news:
            title = n.get("title", "") if isinstance(n, dict) else getattr(n, "title", "")
            url = n.get("url") if isinstance(n, dict) else getattr(n, "url", None)
            source = n.get("source") if isinstance(n, dict) else getattr(n, "source", None)
            summary = n.get("summary") if isinstance(n, dict) else getattr(n, "summary", None)
            tag = n.get("relevance_tag") if isinstance(n, dict) else getattr(n, "relevance_tag", None)

            title_html = (
                f'<a href="{html_lib.escape(url)}" target="_blank" rel="noopener noreferrer">{html_lib.escape(title)}</a>'
                if url else html_lib.escape(title)
            )

            source_html = f'<span class="news-source">{html_lib.escape(source)}</span>' if source else ""
            tag_html = f'<span class="news-tag">{html_lib.escape(tag)}</span>' if tag else ""
            summary_html = f'<div class="news-summary">{html_lib.escape(summary)}</div>' if summary else ""

            items_html.append(
                f'<div class="news-item">'
                f'<div class="news-title">{title_html}{source_html}{tag_html}</div>'
                f'{summary_html}'
                f'</div>'
            )

        return (
            f'<div class="section">'
            f'<div class="section-header"><span class="section-icon">&#x1F916;</span> AI Pulse</div>'
            f'{"".join(items_html)}'
            f'</div>'
        )

    @staticmethod
    def _render_todos_section(todos: Optional[List] = None) -> str:
        """Render the 'This Week' to-dos section."""
        if not todos:
            return ""

        items_html = []
        for t in todos:
            desc = t.get("description", "") if isinstance(t, dict) else getattr(t, "description", "")
            source = t.get("source", "") if isinstance(t, dict) else getattr(t, "source", "")
            person = t.get("person_name") if isinstance(t, dict) else getattr(t, "person_name", None)
            company = t.get("person_company") if isinstance(t, dict) else getattr(t, "person_company", None)

            source_class = {
                "journal": "todo-journal",
                "follow-up": "todo-followup",
                "action-item": "todo-action",
            }.get(source, "todo-action")
            source_label = source.replace("-", " ").title() if source else "Task"

            person_html = ""
            if person:
                person_parts = [html_lib.escape(person)]
                if company:
                    person_parts.append(html_lib.escape(company))
                person_html = f'<div class="todo-person">{" · ".join(person_parts)}</div>'

            items_html.append(
                f'<div class="todo-item">'
                f'<span class="todo-check">&#x25CB;</span>'
                f'<div>'
                f'<span class="todo-desc">{html_lib.escape(desc)}</span>'
                f'<span class="todo-source {html_lib.escape(source_class)}">{html_lib.escape(source_label)}</span>'
                f'{person_html}'
                f'</div>'
                f'</div>'
            )

        return (
            f'<div class="section">'
            f'<div class="section-header"><span class="section-icon">&#x2705;</span> This Week</div>'
            f'{"".join(items_html)}'
            f'</div>'
        )

    def _convert_text_to_html(self, text: str) -> str:
        """Deprecated: kept for compatibility but unused in new renderer."""
        return html_lib.escape(text).replace('\n', '<br>')

    # ------------------------------------------------------------------
    # Journal prompt / reply methods
    # ------------------------------------------------------------------

    def send_journal_prompt(self, to_email: str, meeting_recap_html: str) -> dict:
        """Send the 7pm evening journal prompt email.

        Returns {"message_id": ..., "thread_id": ...} for tracking replies.
        """
        from datetime import datetime as _dt

        date_str = _dt.now().strftime('%A, %B %d')

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1f2937;">
            <div style="background: linear-gradient(135deg, #1e3a5f, #2d5a87); color: white; padding: 20px 24px; border-radius: 12px; margin-bottom: 20px;">
                <div style="font-size: 20px; font-weight: 700;">End of Day Check-in</div>
                <div style="opacity: 0.9; font-size: 13px; margin-top: 4px;">{html_lib.escape(date_str)}</div>
            </div>

            {f'<div style="margin-bottom: 20px;"><div style="font-weight: 600; font-size: 14px; color: #374151; margin-bottom: 8px;">Today&#x27;s meetings:</div>{meeting_recap_html}</div>' if meeting_recap_html else ''}

            <div style="background: #f8fafc; border-left: 3px solid #D6A35C; padding: 16px 20px; border-radius: 0 10px 10px 0; margin-bottom: 16px;">
                <div style="font-weight: 600; color: #1f2937; margin-bottom: 6px;">What's still on your mind?</div>
                <div style="color: #6b7280; font-size: 13px; line-height: 1.5;">
                    Reply with anything — pending tasks, ideas to explore, things to follow up on, areas you want to dig into tomorrow. I'll weave it into your morning brief.
                </div>
            </div>

            <div style="color: #9ca3af; font-size: 11px; margin-top: 20px; padding-top: 12px; border-top: 1px solid #e5e7eb;">
                Just reply to this email. Your response powers tomorrow's newsletter.
            </div>
        </body>
        </html>
        """

        plain_text = (
            f"End of Day Check-in - {date_str}\n\n"
            "What's still on your mind?\n\n"
            "Reply with anything — pending tasks, ideas to explore, things to follow up on. "
            "I'll weave it into your morning brief.\n"
        )

        try:
            message = MIMEMultipart('alternative')
            message['to'] = to_email
            message['subject'] = f"End of Day Check-in - {date_str}"

            message.attach(MIMEText(plain_text, 'plain'))
            message.attach(MIMEText(html_content, 'html'))

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            return {
                "message_id": result.get("id", ""),
                "thread_id": result.get("threadId", ""),
            }

        except Exception as e:
            print(f"[Journal] Error sending journal prompt: {e}")
            return {"message_id": "", "thread_id": ""}

    def get_journal_reply(self, thread_id: str, after_message_id: str) -> Optional[str]:
        """Check a Gmail thread for a reply newer than the original prompt.

        Args:
            thread_id: Gmail thread ID of the journal prompt
            after_message_id: Message ID of the sent prompt (to skip it)

        Returns:
            Parsed body text of the reply, or None if no reply found.
        """
        if not thread_id:
            return None

        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full',
            ).execute()

            messages = thread.get('messages', [])

            # Find messages that are NOT the original prompt
            for msg in messages:
                if msg['id'] == after_message_id:
                    continue

                # This is a reply — extract body
                body_text = self._extract_message_body(msg)
                if body_text and body_text.strip():
                    return body_text.strip()

            return None

        except HttpError as e:
            if e.resp.status == 404:
                print(f"[Journal] Thread {thread_id} not found")
            else:
                print(f"[Journal] HTTP error reading thread: {e}")
            return None
        except Exception as e:
            print(f"[Journal] Error reading journal reply: {e}")
            return None

    @staticmethod
    def _extract_message_body(message: dict) -> Optional[str]:
        """Extract plain text body from a Gmail message."""
        payload = message.get('payload', {})

        # Try to find text/plain part
        def _find_plain(part):
            mime = part.get('mimeType', '')
            if mime == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            for sub in part.get('parts', []):
                result = _find_plain(sub)
                if result:
                    return result
            return None

        text = _find_plain(payload)

        if text:
            # Strip quoted reply content (lines starting with >)
            lines = text.splitlines()
            cleaned = []
            for line in lines:
                # Stop at quoted content markers
                if line.strip().startswith('>'):
                    break
                if line.strip().startswith('On ') and line.strip().endswith('wrote:'):
                    break
                cleaned.append(line)
            return '\n'.join(cleaned).strip()

        return None