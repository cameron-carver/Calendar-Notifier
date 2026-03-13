"""
Type-safe enums for EA mode.

Provides string-based enums for priority levels, relationship strength,
relationship status, and content depth.
"""
from enum import Enum


class Priority(str, Enum):
    """Meeting priority levels for EA annotations."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class RelationshipStrength(str, Enum):
    """Relationship strength levels."""
    NEW = "new"
    DEVELOPING = "developing"
    STRONG = "strong"
    KEY = "key"


class RelationshipStatus(str, Enum):
    """Relationship status/role types."""
    INVESTOR = "investor"
    FOUNDER = "founder"
    ADVISOR = "advisor"
    COINVESTOR = "coinvestor"
    CORPORATE = "corporate"
    SERVICE_PROVIDER = "service_provider"
    INTERNAL = "internal"


class ContentDepth(str, Enum):
    """Brief content depth levels."""
    QUICK = "quick"
    STANDARD = "standard"
    DETAILED = "detailed"
