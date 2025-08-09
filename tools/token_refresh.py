#!/usr/bin/env python3
"""
Token refresh helper for Google Calendar and Gmail credentials.

- Reads credential file paths from environment via app.core.config.settings
- Verifies required scopes for each service
- Refreshes access tokens when possible and writes back to disk

Usage:
  python tools/token_refresh.py

Exit codes:
  0 = success, non-zero = warnings/errors printed
"""

import json
import sys
from pathlib import Path
from typing import List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.core.config import settings
from app.services.calendar.google_calendar import GoogleCalendarService
from app.services.email.gmail_service import GmailService


def load_creds(path: str, required_scopes: List[str]) -> Credentials | None:
    p = Path(path)
    if not p.exists():
        print(f"❌ Credentials file missing: {p}")
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(p), required_scopes)
        return creds
    except Exception as e:
        print(f"❌ Failed to load credentials {p}: {e}")
        return None


def ensure_scopes(creds: Credentials, required_scopes: List[str]) -> bool:
    present = set(creds.scopes or [])
    missing = [s for s in required_scopes if s not in present]
    if missing:
        print("⚠️  Missing scopes:", ", ".join(missing))
        return False
    return True


def refresh_if_needed(creds: Credentials, path: str) -> bool:
    try:
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
            Path(path).write_text(creds.to_json())
            print(f"✅ Refreshed token and saved: {path}")
            return True
        elif creds.valid:
            print(f"✅ Token valid: {path}")
            return True
        else:
            print(f"⚠️  Cannot refresh token (no refresh_token present): {path}")
            return False
    except Exception as e:
        print(f"❌ Refresh failed for {path}: {e}")
        return False


def main() -> int:
    calendar_scopes = GoogleCalendarService.SCOPES
    gmail_scopes = GmailService.SCOPES

    cal_path = settings.google_calendar_credentials_file
    gmail_path = settings.gmail_credentials_file

    print("🔐 Checking Calendar credentials:")
    cal_creds = load_creds(cal_path, calendar_scopes)
    ok = True
    if cal_creds:
        ok &= ensure_scopes(cal_creds, calendar_scopes)
        ok &= refresh_if_needed(cal_creds, cal_path)
    else:
        ok = False

    print("\n🔐 Checking Gmail credentials:")
    gm_creds = load_creds(gmail_path, gmail_scopes)
    if gm_creds:
        ok &= ensure_scopes(gm_creds, gmail_scopes)
        ok &= refresh_if_needed(gm_creds, gmail_path)
    else:
        ok = False

    if not ok:
        print("\nNext steps: Run setup_oauth.py to re-consent with required scopes.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

