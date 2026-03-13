"""Text cleaning utilities for calendar event descriptions."""

from __future__ import annotations

import re
from typing import Optional


# Patterns to strip from calendar event descriptions (Zoom, Calendly, Google Meet, Teams)
_BOILERPLATE_PATTERNS = [
    # Zoom join blocks
    re.compile(
        r"(?:─+\s*)?(?:Join Zoom Meeting|You can join this meeting from your computer).*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"https?://\S*zoom\.us/\S+", re.IGNORECASE),
    re.compile(
        r"Meeting ID:\s*\d[\d\s]+(?:Passcode:\s*\S+)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"One tap mobile.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE
    ),
    re.compile(
        r"Dial by your location.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE
    ),
    # Google Meet
    re.compile(
        r"(?:Join with Google Meet|Got a question\?).*", re.DOTALL | re.IGNORECASE
    ),
    re.compile(r"https?://meet\.google\.com/\S+", re.IGNORECASE),
    # Microsoft Teams
    re.compile(
        r"(?:Join Microsoft Teams Meeting|Join on your computer).*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"https?://teams\.microsoft\.com/\S+", re.IGNORECASE),
    # Webex
    re.compile(r"(?:Join Webex Meeting).*", re.DOTALL | re.IGNORECASE),
    # Calendly boilerplate
    re.compile(
        r"Event Type:\s*\n.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE
    ),
    re.compile(
        r"Invitee Time Zone:.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE
    ),
    re.compile(
        r"Location:\s*(?:This is a (?:Zoom|Google Meet|Microsoft Teams) web conference).*?(?=\n\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    # Calendly "Event Name\n30 Minute Meeting" blocks
    re.compile(r"^Event Name\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\d+\s+Minute\s+Meeting\s*$", re.MULTILINE | re.IGNORECASE),
    # "Powered by Calendly" line
    re.compile(r"Powered by Calendly.*", re.IGNORECASE),
    # Calendly cancel/reschedule links
    re.compile(r"Need to make changes to this event\?.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE),
    re.compile(r"(?:Cancel|Reschedule):\s*https?://calendly\.com/\S+", re.IGNORECASE),
    # Password lines
    re.compile(r"^Password:\s*\S+\s*$", re.MULTILINE | re.IGNORECASE),
    # Generic "This is a Zoom/video meeting" lines
    re.compile(
        r"This is a (?:Zoom|Google Meet|Microsoft Teams|Webex) (?:web )?(?:conference|meeting)\.?",
        re.IGNORECASE,
    ),
    # HTML tags
    re.compile(r"<[^>]+>"),
    # Horizontal rules / dividers
    re.compile(r"[-─═]{4,}"),
]

# Calendly structured fields we want to KEEP (extract the value)
_CALENDLY_USEFUL = re.compile(
    r"(?:Additional (?:info|information|notes)|Notes|What would you like to discuss\?|Description|Agenda|Please share anything[^:.\n]*)[.:]*\s*(.+?)(?=\n(?:[A-Z][\w\s]+:)|\n\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def clean_calendar_description(raw: Optional[str]) -> Optional[str]:
    """Strip conferencing boilerplate from a calendar event description.

    Returns cleaned text, or None if nothing useful remains.
    """
    if not raw:
        return None

    text = raw.strip()

    # First, try to extract Calendly structured content (notes, agenda)
    useful_parts = []
    for m in _CALENDLY_USEFUL.finditer(text):
        snippet = m.group(1).strip()
        if snippet and len(snippet) > 5:
            useful_parts.append(snippet)

    # Strip all boilerplate patterns
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    # If Calendly extraction found useful content, prefer that
    if useful_parts:
        combined = " | ".join(useful_parts)
        # Also include remaining cleaned text if it adds info
        if text and text not in combined and len(text) > 10:
            combined = f"{combined}\n{text}"
        return combined.strip() or None

    # Return cleaned text only if it has real content
    if not text or len(text) < 5:
        return None

    return text
