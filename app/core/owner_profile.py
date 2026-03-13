"""Owner profile — defines 'who I am' for persona-aware meeting prep."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class OwnerProfile:
    """Identity of the calendar owner used to personalise briefs."""

    name: str
    title: str
    company: str
    focus: str  # Investment thesis / areas of focus
    email: str
    linkedin: str = ""

    @property
    def domain(self) -> str:
        """Extract email domain."""
        if "@" in self.email:
            return self.email.split("@", 1)[1].lower()
        return ""

    @property
    def short_name(self) -> str:
        """First name for casual references."""
        return self.name.split()[0] if self.name else ""

    def summary_line(self) -> str:
        """One-liner for AI prompts: 'Cameron Carver, Principal at Blackhorn VC'."""
        parts = [self.name]
        if self.title:
            parts.append(self.title)
        if self.company:
            parts[-1] += f" at {self.company}"
        return ", ".join(parts)


def load_owner_profile() -> OwnerProfile:
    """Build an OwnerProfile from application settings."""
    return OwnerProfile(
        name=settings.owner_name,
        title=settings.owner_title,
        company=settings.owner_company,
        focus=settings.owner_focus,
        email=settings.owner_email or (settings.google_calendar_ids or "").split(",")[0].strip(),
        linkedin=settings.owner_linkedin,
    )


# Singleton — import this where needed
owner_profile = load_owner_profile()
