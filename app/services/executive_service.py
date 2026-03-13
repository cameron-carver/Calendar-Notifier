"""
Service for managing executives in EA mode.

Handles CRUD operations for executive profiles, calendar configuration,
and delivery preferences.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.brief import Executive
from app.core.config import settings


class ExecutiveService:
    """Service for executive profile management."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_executive(
        self,
        name: str,
        email: str,
        google_calendar_ids: List[str],
        title: Optional[str] = None,
        timezone: str = "America/New_York",
        delivery_time: str = "08:00",
        **kwargs
    ) -> Executive:
        """
        Create a new executive profile.

        Args:
            name: Executive's full name
            email: Executive's email address (unique)
            google_calendar_ids: List of Google Calendar IDs to aggregate
            title: Executive's title (e.g., "Managing Partner")
            timezone: Executive's timezone for delivery
            delivery_time: Default delivery time in HH:MM format
            **kwargs: Additional optional fields (content_depth, feature toggles, etc.)

        Returns:
            Created Executive instance

        Raises:
            ValueError: If email already exists
        """
        # Check for duplicate email
        existing = self.db.query(Executive).filter(
            Executive.email == email
        ).first()

        if existing:
            raise ValueError(f"Executive with email {email} already exists")

        # Create executive
        executive = Executive(
            name=name,
            email=email,
            title=title,
            google_calendar_ids=google_calendar_ids,
            timezone=timezone,
            delivery_time=delivery_time,
            is_active=True,
            **kwargs
        )

        self.db.add(executive)
        self.db.commit()
        self.db.refresh(executive)

        return executive

    def get_executive(self, executive_id: int) -> Optional[Executive]:
        """
        Get executive by ID.

        Args:
            executive_id: Executive ID

        Returns:
            Executive instance or None if not found
        """
        return self.db.query(Executive).filter(
            Executive.id == executive_id
        ).first()

    def get_executive_by_email(self, email: str) -> Optional[Executive]:
        """
        Get executive by email.

        Args:
            email: Executive's email address

        Returns:
            Executive instance or None if not found
        """
        return self.db.query(Executive).filter(
            Executive.email == email
        ).first()

    def list_executives(
        self,
        active_only: bool = True
    ) -> List[Executive]:
        """
        List all executives.

        Args:
            active_only: If True, only return active executives

        Returns:
            List of Executive instances
        """
        query = self.db.query(Executive)

        if active_only:
            query = query.filter(Executive.is_active == True)

        return query.order_by(Executive.name).all()

    def update_executive(
        self,
        executive_id: int,
        **updates
    ) -> Optional[Executive]:
        """
        Update executive profile.

        Args:
            executive_id: Executive ID
            **updates: Fields to update

        Returns:
            Updated Executive instance or None if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return None

        # Update fields
        for field, value in updates.items():
            if hasattr(executive, field):
                setattr(executive, field, value)

        self.db.commit()
        self.db.refresh(executive)

        return executive

    def delete_executive(self, executive_id: int) -> bool:
        """
        Soft delete executive (set is_active to False).

        Args:
            executive_id: Executive ID

        Returns:
            True if deleted, False if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return False

        executive.is_active = False
        self.db.commit()

        return True

    def hard_delete_executive(self, executive_id: int) -> bool:
        """
        Permanently delete executive from database.

        WARNING: This will cascade delete all related briefs, annotations,
        and relationships. Use with caution.

        Args:
            executive_id: Executive ID

        Returns:
            True if deleted, False if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return False

        self.db.delete(executive)
        self.db.commit()

        return True

    def get_calendar_ids(self, executive_id: int) -> List[str]:
        """
        Get all calendar IDs for an executive.

        Args:
            executive_id: Executive ID

        Returns:
            List of Google Calendar IDs or empty list if not found
        """
        executive = self.get_executive(executive_id)

        if not executive or not executive.google_calendar_ids:
            return []

        return executive.google_calendar_ids

    def add_calendar(
        self,
        executive_id: int,
        calendar_id: str
    ) -> Optional[Executive]:
        """
        Add a calendar to executive's calendar list.

        Args:
            executive_id: Executive ID
            calendar_id: Google Calendar ID to add

        Returns:
            Updated Executive instance or None if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return None

        # Initialize if needed
        if not executive.google_calendar_ids:
            executive.google_calendar_ids = []

        # Avoid duplicates
        if calendar_id not in executive.google_calendar_ids:
            calendar_ids = executive.google_calendar_ids.copy()
            calendar_ids.append(calendar_id)
            executive.google_calendar_ids = calendar_ids
            self.db.commit()
            self.db.refresh(executive)

        return executive

    def remove_calendar(
        self,
        executive_id: int,
        calendar_id: str
    ) -> Optional[Executive]:
        """
        Remove a calendar from executive's calendar list.

        Args:
            executive_id: Executive ID
            calendar_id: Google Calendar ID to remove

        Returns:
            Updated Executive instance or None if not found
        """
        executive = self.get_executive(executive_id)

        if not executive or not executive.google_calendar_ids:
            return None

        if calendar_id in executive.google_calendar_ids:
            calendar_ids = executive.google_calendar_ids.copy()
            calendar_ids.remove(calendar_id)
            executive.google_calendar_ids = calendar_ids
            self.db.commit()
            self.db.refresh(executive)

        return executive

    def get_delivery_schedule(
        self,
        executive_id: int,
        day_of_week: Optional[str] = None
    ) -> Optional[str]:
        """
        Get delivery time for executive, optionally for a specific day.

        Args:
            executive_id: Executive ID
            day_of_week: Day of week (e.g., "monday"). If None, returns default.

        Returns:
            Delivery time in HH:MM format or None if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return None

        # Check for day-specific schedule
        if day_of_week and executive.delivery_schedule:
            day_time = executive.delivery_schedule.get(day_of_week.lower())
            if day_time:
                return day_time

            # Fall back to default in schedule
            default_time = executive.delivery_schedule.get("default")
            if default_time:
                return default_time

        # Fall back to delivery_time column
        return executive.delivery_time or "08:00"

    def update_delivery_schedule(
        self,
        executive_id: int,
        schedule: dict
    ) -> Optional[Executive]:
        """
        Update executive's delivery schedule.

        Args:
            executive_id: Executive ID
            schedule: Dictionary with day-specific times
                     e.g., {"monday": "07:00", "friday": "09:00", "default": "08:00"}

        Returns:
            Updated Executive instance or None if not found
        """
        executive = self.get_executive(executive_id)

        if not executive:
            return None

        executive.delivery_schedule = schedule
        self.db.commit()
        self.db.refresh(executive)

        return executive
