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
from app.schemas.brief import MeetingEvent, AttendeeInfo
from dateutil import parser as dateutil_parser


class GmailService:
    """Service for sending emails via Gmail API."""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']
    
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
    
    def create_html_brief(self, content: str, events: Optional[List[MeetingEvent]] = None) -> str:
        """Render a clean, newsletter-style HTML from the concise text brief.
        If `events` are provided, use structured data (including LinkedIn links) instead of regex parsing.
        """
        lines = [ln.strip() for ln in content.splitlines()]
        title = "🌅 Morning Brief"
        subtitle = "Your daily meeting preparation summary"
        items = []

        def normalize_name(raw: str) -> str:
            if not raw:
                return ""
            first = raw.strip().split()[0]
            return first[:1].upper() + first[1:]

        # Extract title/subtitle from first non-empty lines, keep defaults if missing
        non_empty = [ln for ln in lines if ln]
        if non_empty:
            title = html_lib.escape(non_empty[0])
        if len(non_empty) > 1:
            subtitle = html_lib.escape(non_empty[1])

        # If events are available, build items from structured data to include LinkedIn links
        if events:
            for ev in events:
                time_range = f"{ev.start_time.strftime('%I:%M %p').lstrip('0')}–{ev.end_time.strftime('%I:%M %p').lstrip('0')}"
                attendees_html_parts = []
                for att in ev.attendees[:8]:
                    name = normalize_name(att.name or att.email.split('@')[0])
                    linkedin = getattr(att, 'linkedin_url', None)
                    # Fallback: Google search link to LinkedIn profile if none provided
                    if not linkedin:
                        q = name
                        company = getattr(att, 'company', None)
                        if company:
                            q += f" {company}"
                        q += " linkedin"
                        linkedin = f"https://www.google.com/search?q={html_lib.escape(q)}"
                    attendees_html_parts.append(
                        '<a href="' + linkedin + '" target="_blank" rel="noopener noreferrer">' + html_lib.escape(name) + '<span class="li-icon">↗</span></a>'
                    )
                attendees_joined = ", ".join(attendees_html_parts)
                about_text = ""
                # Prefer last note summary, else recent email/context, else description
                for att in ev.attendees:
                    if getattr(att, 'last_note_summary', None):
                        about_text = att.last_note_summary
                        break
                if not about_text and ev.description:
                    about_text = re.sub(r"<[^>]+>", " ", html_lib.unescape(ev.description))
                about_text = (about_text[:120] + "…") if about_text and len(about_text) > 120 else about_text

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

                # Meeting size chip
                count = len(ev.attendees)
                if count >= 8:
                    chip_class = 'chip-large'
                elif count >= 4:
                    chip_class = 'chip-medium'
                else:
                    chip_class = 'chip-small'
                chip_html = f"<span class=\"chip {chip_class}\">{count} attendee{'s' if count != 1 else ''}</span>"

                # Collect materials URLs from attendees (Affinity)
                materials_urls = []
                for att in ev.attendees:
                    urls = getattr(att, 'materials', None) or []
                    for u in urls:
                        if u not in materials_urls:
                            materials_urls.append(u)
                materials_urls = materials_urls[:3]

                items.append({
                    "time": html_lib.escape(time_range),
                    "title": html_lib.escape(ev.title or "Untitled Meeting"),
                    "attendees_html": attendees_joined,
                    "about": html_lib.escape(about_text) if about_text else "",
                    "context": html_lib.escape(context_text) if context_text else "",
                    "size_chip": chip_html,
                    "materials": materials_urls,
                })
        else:
            # Regex to parse meeting one-liners produced by fallback formatter
            pattern = re.compile(r"^📅\s*(\d{1,2}:\d{2}\s*[AP]M–\d{1,2}:\d{2}\s*[AP]M)\s+(.*?)(?:\s+—\s+(.*?))?(?:\s+— About:\s+(.*))?$")

            for ln in lines:
                if not ln.startswith("📅 "):
                    continue
                m = pattern.match(ln)
                if not m:
                    # Fallback: just show the line
                    items.append({
                        "time": "",
                        "title": html_lib.escape(ln.replace('📅', '').strip()),
                        "attendees_html": "",
                        "about": "",
                    })
                    continue
                time_range, title_txt, attendees_txt, about_txt = m.groups()
                items.append({
                    "time": html_lib.escape(time_range or ""),
                    "title": html_lib.escape(title_txt or ""),
                    "attendees_html": html_lib.escape(attendees_txt or ""),
                    "about": html_lib.escape((about_txt or "").rstrip(".")),
                })

        # Build newsletter HTML
        items_html = []
        for it in items:
            attendees_html = f"<span class=\"attendees\">— {it['attendees_html']}</span>" if it.get("attendees_html") else ""
            about_html = f"<div class=\"about\">About: {it['about']}</div>" if it["about"] else ""
            context_html = f"<div class=\"about\">{it['context']}</div>" if it.get("context") else ""
            # Materials row (compact) if present
            materials_html = ""
            if it.get('materials'):
                links = []
                for u in it['materials']:
                    esc = html_lib.escape(u)
                    links.append(f'<a href="{esc}" target="_blank" rel="noopener noreferrer">link</a>')
                materials_html = f"<div class=\"materials\">Materials: {' • '.join(links)}</div>"

            items_html.append(
                f"""
                <li class="item">
                    <span class="time">{it['time']}</span>
                    <span class="dot">•</span>
                    <span class="title">{it['title']}</span> {it.get('size_chip','')}
                    {attendees_html}
                    {about_html}
                    {context_html}
                    {materials_html}
                </li>
                """
            )

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
                    --line: #eef2f7;
                    --accent: {html_lib.escape(settings.theme_accent)}; /* accent */
                    --accent2: {html_lib.escape(settings.theme_accent2)}; /* secondary */
                    --chip-bg: #eef2ff; /* indigo-50 */
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
                .header {{
                    margin-bottom: 16px;
                }}
                .header h1 {{
                    margin: 0 0 6px 0;
                    font-size: 24px;
                    letter-spacing: 0.2px;
                }}
                .header p {{
                    margin: 0;
                    color: var(--muted);
                    font-size: 13px;
                }}
                .bar {{
                    height: 6px;
                    width: 100%;
                    background: linear-gradient(90deg, var(--accent), var(--accent2));
                    border-radius: 999px;
                    margin: 8px 0 14px 0;
                }}
                ul.list {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }}
                .item {{
                    padding: 14px 0;
                    border-top: 1px solid var(--line);
                }}
                .item:first-child {{
                    border-top: 0;
                }}
                .time {{
                    color: var(--accent);
                    font-weight: 600;
                    font-size: 12px;
                    background: var(--chip-bg);
                    border: 1px solid rgba(99,102,241,0.22);
                    padding: 4px 8px;
                    border-radius: 999px;
                }}
                .dot {{
                    color: #c7cbd1;
                    margin: 0 8px;
                }}
                .title {{
                    font-weight: 700;
                    font-size: 14px;
                }}
                .chip {{
                    margin-left: 8px;
                    font-size: 11px;
                    padding: 2px 8px;
                    border-radius: 999px;
                    border: 1px solid transparent;
                }}
                .chip-small {{
                    background: #ecfdf5;
                    color: #065f46;
                    border-color: rgba(16,185,129,0.25);
                }}
                .chip-medium {{
                    background: #fffbeb;
                    color: #92400e;
                    border-color: rgba(245,158,11,0.25);
                }}
                .chip-large {{
                    background: #fef2f2;
                    color: #991b1b;
                    border-color: rgba(239,68,68,0.25);
                }}
                .attendees {{
                    color: #374151;
                    margin-left: 8px;
                    font-size: 13px;
                }}
                .li-icon {{
                    font-size: 11px;
                    margin-left: 2px;
                    color: #6b7280;
                }}
                .about {{
                    color: var(--muted);
                    font-size: 12.5px;
                    margin-top: 6px;
                }}
                .footer {{
                    margin-top: 22px;
                    padding-top: 12px;
                    border-top: 1px solid var(--line);
                    color: var(--muted);
                    font-size: 12px;
                }}
                .materials {{
                    margin-top: 4px;
                    font-size: 12px;
                    color: var(--muted);
                }}
                .materials a {{
                    color: var(--accent);
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div style="background: linear-gradient(90deg, var(--accent), var(--accent2)); color: white; padding: 22px; border-radius: 14px; display: flex; align-items: center; gap: 14px;">
                    <div style="font-size: 28px;">🌅</div>
                    <div>
                        <div style="font-size: 24px; font-weight: 800; letter-spacing: 0.2px;">Morning Brief</div>
                        <div style="opacity: 0.95; font-size: 13px;">Your daily meeting preparation summary</div>
                    </div>
                </div>
            </div>
            <ul class="list">
                {''.join(items_html)}
            </ul>
            <div class="footer">Generated by Morning Brief</div>
        </body>
        </html>
        """
        return html_template
    
    def _convert_text_to_html(self, text: str) -> str:
        """Deprecated: kept for compatibility but unused in new renderer."""
        return html_lib.escape(text).replace('\n', '<br>')