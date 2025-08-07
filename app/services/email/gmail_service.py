import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Optional
from app.core.config import settings


class GmailService:
    """Service for sending emails via Gmail API."""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.send']
    
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
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
    
    def create_html_brief(self, content: str) -> str:
        """Convert plain text brief to HTML format."""
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .meeting {{
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 4px;
                }}
                .attendee {{
                    background: white;
                    padding: 10px;
                    margin: 10px 0;
                    border-radius: 4px;
                    border: 1px solid #e9ecef;
                }}
                .news-item {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    padding: 10px;
                    margin: 5px 0;
                    border-radius: 4px;
                }}
                .time {{
                    color: #6c757d;
                    font-size: 0.9em;
                }}
                .company {{
                    color: #495057;
                    font-weight: 500;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🌅 Morning Brief</h1>
                <p>Your daily meeting preparation summary</p>
            </div>
            
            <div class="content">
                {self._convert_text_to_html(content)}
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e9ecef; color: #6c757d; font-size: 0.9em;">
                <p>Generated by Morning Brief - Calendar Notifier</p>
            </div>
        </body>
        </html>
        """
        
        return html_template
    
    def _convert_text_to_html(self, text: str) -> str:
        """Convert plain text to HTML with basic formatting."""
        # Convert line breaks
        html = text.replace('\n', '<br>')
        
        # Convert meeting titles (lines starting with 📅)
        html = html.replace('📅 ', '<div class="meeting"><h3>📅 ')
        html = html.replace('<br>   Time:', '</h3><p class="time">⏰ ')
        html = html.replace('<br>   Location:', '</p><p>📍 ')
        html = html.replace('<br>   Attendees:', '</p><p><strong>👥 Attendees:</strong></p>')
        
        # Convert attendee lines
        html = html.replace('<br>     - ', '<div class="attendee">• ')
        html = html.replace(' (', '<span class="company"> (')
        html = html.replace(')<br>', ')</span></div>')
        
        # Convert news items
        html = html.replace('<br>      - ', '<div class="news-item">📰 ')
        html = html.replace('<br>    Recent news:', '</div><p><strong>📰 Recent News:</strong></p>')
        
        return html 