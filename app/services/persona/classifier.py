"""Attendee persona classification based on domain patterns and title heuristics."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Set

from app.core.config import settings
from app.core.owner_profile import OwnerProfile
from app.schemas.brief import AttendeeInfo


class PersonaType(str, Enum):
    """Classification of a meeting attendee relative to the calendar owner."""

    FOUNDER = "founder"
    COINVESTOR = "coinvestor"
    LP = "lp"
    CORPORATE = "corporate"
    SERVICE_PROVIDER = "service_provider"
    INTERNAL = "internal"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        """Human-friendly label for display."""
        return {
            "founder": "Founder",
            "coinvestor": "Co-investor",
            "lp": "LP",
            "corporate": "Corporate",
            "service_provider": "Service",
            "internal": "Internal",
            "unknown": "",
        }[self.value]

    @property
    def color(self) -> str:
        """Hex background color for email badge chips."""
        return {
            "founder": "#dcfce7",       # green-100
            "coinvestor": "#dbeafe",     # blue-100
            "lp": "#f3e8ff",            # purple-100
            "corporate": "#ffedd5",     # orange-100
            "service_provider": "#f3f4f6",  # gray-100
            "internal": "#f9fafb",      # gray-50
            "unknown": "#f9fafb",
        }[self.value]

    @property
    def text_color(self) -> str:
        """Hex text color for email badge chips."""
        return {
            "founder": "#166534",       # green-800
            "coinvestor": "#1e40af",    # blue-800
            "lp": "#6b21a8",           # purple-800
            "corporate": "#9a3412",    # orange-800
            "service_provider": "#374151",  # gray-700
            "internal": "#6b7280",     # gray-500
            "unknown": "#6b7280",
        }[self.value]


def _parse_domain_set(csv: Optional[str]) -> Set[str]:
    """Parse a comma-separated string into a lowercase set of domains."""
    if not csv:
        return set()
    return {d.strip().lower() for d in csv.split(",") if d.strip()}


def _extract_domain(email: str) -> str:
    if "@" in email:
        return email.split("@", 1)[1].lower()
    return ""


class PersonaClassifier:
    """Classify attendees into persona types using domain patterns and title heuristics."""

    def __init__(self, owner: OwnerProfile) -> None:
        self.owner = owner
        self.owner_domain = owner.domain

        # Internal domains: owner domain + any configured extras
        self.internal_domains: Set[str] = {self.owner_domain} if self.owner_domain else set()
        self.internal_domains |= _parse_domain_set(settings.internal_domains)

        # Explicit domain lists from config
        self.portfolio_domains: Set[str] = _parse_domain_set(settings.persona_portfolio_domains)
        self.lp_domains: Set[str] = _parse_domain_set(settings.persona_lp_domains)
        self.service_domains: Set[str] = _parse_domain_set(settings.persona_service_domains)

        # Coinvestor domain substrings (e.g. ".vc", "ventures")
        self.coinvestor_patterns = [
            p.strip().lower()
            for p in (settings.persona_coinvestor_patterns or "").split(",")
            if p.strip()
        ]

        # Title-based heuristics (compiled once)
        self._founder_title_re = re.compile(
            r"\b(founder|co-founder|cofounder|ceo|chief executive)\b", re.IGNORECASE
        )
        self._coinvestor_title_re = re.compile(
            r"\b(partner|principal|managing director|venture|investor|gp|general partner)\b",
            re.IGNORECASE,
        )
        self._service_title_re = re.compile(
            r"\b(attorney|lawyer|counsel|accountant|auditor|banker|advisor)\b",
            re.IGNORECASE,
        )

    def classify(self, attendee: AttendeeInfo) -> PersonaType:
        """Determine the persona type for an attendee.

        Priority order:
        1. Internal (domain match)
        2. Explicit portfolio domain → FOUNDER
        3. Explicit LP domain → LP
        4. Explicit service domain → SERVICE_PROVIDER
        5. Coinvestor domain pattern → COINVESTOR
        6. Title heuristics (founder titles, VC titles, service titles)
        7. Fallback → CORPORATE if company present, else UNKNOWN
        """
        domain = _extract_domain(attendee.email)
        title = attendee.title or ""
        company = attendee.company or ""

        # 1. Internal
        if domain and domain in self.internal_domains:
            return PersonaType.INTERNAL

        # 2. Portfolio domain → Founder
        if domain and domain in self.portfolio_domains:
            return PersonaType.FOUNDER

        # 3. LP domain
        if domain and domain in self.lp_domains:
            return PersonaType.LP

        # 4. Service domain
        if domain and domain in self.service_domains:
            return PersonaType.SERVICE_PROVIDER

        # 5. Coinvestor domain pattern
        if domain:
            for pattern in self.coinvestor_patterns:
                if pattern in domain:
                    return PersonaType.COINVESTOR

        # 6. Title heuristics
        if title:
            if self._founder_title_re.search(title):
                return PersonaType.FOUNDER
            if self._coinvestor_title_re.search(title):
                return PersonaType.COINVESTOR
            if self._service_title_re.search(title):
                return PersonaType.SERVICE_PROVIDER

        # 7. Fallback
        if company:
            return PersonaType.CORPORATE

        return PersonaType.UNKNOWN
