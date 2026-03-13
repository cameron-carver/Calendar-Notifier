"""
Service for managing person relationships in EA mode.

Tracks relationships between executives and meeting attendees,
including relationship strength, personal context, and follow-up cadence.
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models.brief import PersonRelationship


class RelationshipService:
    """Service for person relationship management."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_or_update_relationship(
        self,
        executive_id: int,
        person_email: str,
        person_name: Optional[str] = None,
        person_company: Optional[str] = None,
        **kwargs
    ) -> PersonRelationship:
        """
        Create or update relationship record.

        Args:
            executive_id: Executive ID
            person_email: Attendee email address
            person_name: Attendee name
            person_company: Attendee company
            **kwargs: Additional fields (relationship_strength, notes, etc.)

        Returns:
            PersonRelationship instance
        """
        # Check if relationship exists
        existing = self.get_relationship(executive_id, person_email)

        if existing:
            # Update existing
            for field, value in kwargs.items():
                if hasattr(existing, field) and value is not None:
                    setattr(existing, field, value)

            if person_name:
                existing.person_name = person_name
            if person_company:
                existing.person_company = person_company

            self.db.commit()
            self.db.refresh(existing)
            return existing

        # Create new relationship
        # Set default strength if not provided in kwargs
        if 'relationship_strength' not in kwargs:
            kwargs['relationship_strength'] = "new"
        if 'total_meetings' not in kwargs:
            kwargs['total_meetings'] = 0

        relationship = PersonRelationship(
            executive_id=executive_id,
            person_email=person_email,
            person_name=person_name,
            person_company=person_company,
            **kwargs
        )

        self.db.add(relationship)
        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def get_relationship(
        self,
        executive_id: int,
        person_email: str
    ) -> Optional[PersonRelationship]:
        """
        Get relationship record.

        Args:
            executive_id: Executive ID
            person_email: Attendee email

        Returns:
            PersonRelationship instance or None if not found
        """
        return self.db.query(PersonRelationship).filter(
            and_(
                PersonRelationship.executive_id == executive_id,
                PersonRelationship.person_email == person_email
            )
        ).first()

    def get_relationship_by_id(
        self,
        relationship_id: int
    ) -> Optional[PersonRelationship]:
        """
        Get relationship by ID.

        Args:
            relationship_id: Relationship ID

        Returns:
            PersonRelationship instance or None if not found
        """
        return self.db.query(PersonRelationship).filter(
            PersonRelationship.id == relationship_id
        ).first()

    def list_relationships(
        self,
        executive_id: int,
        relationship_strength: Optional[str] = None,
        relationship_status: Optional[str] = None
    ) -> List[PersonRelationship]:
        """
        List relationships for an executive.

        Args:
            executive_id: Executive ID
            relationship_strength: Filter by strength ("new" | "developing" | "strong" | "key")
            relationship_status: Filter by status (e.g., "investor", "founder")

        Returns:
            List of PersonRelationship instances
        """
        query = self.db.query(PersonRelationship).filter(
            PersonRelationship.executive_id == executive_id
        )

        if relationship_strength:
            query = query.filter(
                PersonRelationship.relationship_strength == relationship_strength
            )

        if relationship_status:
            query = query.filter(
                PersonRelationship.relationship_status == relationship_status
            )

        return query.order_by(
            PersonRelationship.last_met_date.desc()
        ).all()

    def update_relationship(
        self,
        relationship_id: int,
        **updates
    ) -> Optional[PersonRelationship]:
        """
        Update relationship fields.

        Args:
            relationship_id: Relationship ID
            **updates: Fields to update

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship_by_id(relationship_id)

        if not relationship:
            return None

        # Update fields
        for field, value in updates.items():
            if hasattr(relationship, field):
                setattr(relationship, field, value)

        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def delete_relationship(self, relationship_id: int) -> bool:
        """
        Delete relationship record.

        Args:
            relationship_id: Relationship ID

        Returns:
            True if deleted, False if not found
        """
        relationship = self.get_relationship_by_id(relationship_id)

        if not relationship:
            return False

        self.db.delete(relationship)
        self.db.commit()

        return True

    def record_meeting(
        self,
        executive_id: int,
        person_email: str,
        meeting_date: datetime,
        person_name: Optional[str] = None,
        person_company: Optional[str] = None
    ) -> PersonRelationship:
        """
        Record a meeting occurrence, updating relationship history.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            meeting_date: Meeting date/time
            person_name: Attendee name (to cache)
            person_company: Attendee company (to cache)

        Returns:
            Updated PersonRelationship instance
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            # First meeting - create relationship
            relationship = self.create_or_update_relationship(
                executive_id=executive_id,
                person_email=person_email,
                person_name=person_name,
                person_company=person_company,
                first_met_date=meeting_date,
                last_met_date=meeting_date,
                total_meetings=1
            )
        else:
            # Update meeting history
            if not relationship.first_met_date:
                relationship.first_met_date = meeting_date

            relationship.last_met_date = meeting_date
            relationship.total_meetings = (relationship.total_meetings or 0) + 1

            # Update cached name/company if provided
            if person_name:
                relationship.person_name = person_name
            if person_company:
                relationship.person_company = person_company

            self.db.commit()
            self.db.refresh(relationship)

        return relationship

    def set_relationship_strength(
        self,
        executive_id: int,
        person_email: str,
        strength: str
    ) -> Optional[PersonRelationship]:
        """
        Set relationship strength.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            strength: Strength level ("new" | "developing" | "strong" | "key")

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        relationship.relationship_strength = strength
        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def set_relationship_status(
        self,
        executive_id: int,
        person_email: str,
        status: str
    ) -> Optional[PersonRelationship]:
        """
        Set relationship status/role.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            status: Status/role (e.g., "investor", "founder", "advisor")

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        relationship.relationship_status = status
        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def add_relationship_notes(
        self,
        executive_id: int,
        person_email: str,
        notes: str,
        append: bool = False
    ) -> Optional[PersonRelationship]:
        """
        Add or update relationship notes.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            notes: Relationship context notes
            append: If True, append to existing notes instead of replacing

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        if append and relationship.relationship_notes:
            relationship.relationship_notes += f"\n\n{notes}"
        else:
            relationship.relationship_notes = notes

        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def add_personal_details(
        self,
        executive_id: int,
        person_email: str,
        details: dict
    ) -> Optional[PersonRelationship]:
        """
        Add or update personal details.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            details: Dictionary of personal details (interests, family, etc.)

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        # Merge with existing details
        if relationship.personal_details:
            existing_details = relationship.personal_details.copy()
            existing_details.update(details)
            relationship.personal_details = existing_details
        else:
            relationship.personal_details = details

        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def set_follow_up_cadence(
        self,
        executive_id: int,
        person_email: str,
        cadence_days: int,
        next_follow_up: Optional[datetime] = None
    ) -> Optional[PersonRelationship]:
        """
        Set follow-up cadence for a relationship.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            cadence_days: Suggested cadence in days
            next_follow_up: Optional next follow-up date (auto-calculates if not provided)

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        relationship.follow_up_cadence_days = cadence_days

        # Auto-calculate next follow-up if not provided
        if not next_follow_up:
            if relationship.last_met_date:
                next_follow_up = relationship.last_met_date + timedelta(days=cadence_days)
            else:
                next_follow_up = datetime.now() + timedelta(days=cadence_days)

        relationship.next_follow_up = next_follow_up

        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def record_follow_up(
        self,
        executive_id: int,
        person_email: str,
        follow_up_date: Optional[datetime] = None
    ) -> Optional[PersonRelationship]:
        """
        Record that a follow-up occurred.

        Args:
            executive_id: Executive ID
            person_email: Attendee email
            follow_up_date: When follow-up occurred (default: now)

        Returns:
            Updated PersonRelationship instance or None if not found
        """
        relationship = self.get_relationship(executive_id, person_email)

        if not relationship:
            return None

        if not follow_up_date:
            follow_up_date = datetime.now()

        relationship.last_follow_up = follow_up_date

        # Calculate next follow-up if cadence is set
        if relationship.follow_up_cadence_days:
            relationship.next_follow_up = follow_up_date + timedelta(
                days=relationship.follow_up_cadence_days
            )

        self.db.commit()
        self.db.refresh(relationship)

        return relationship

    def get_relationships_needing_follow_up(
        self,
        executive_id: int,
        before_date: Optional[datetime] = None
    ) -> List[PersonRelationship]:
        """
        Get relationships that need follow-up.

        Args:
            executive_id: Executive ID
            before_date: Optional date filter (get follow-ups before this date)
                        Default: now

        Returns:
            List of PersonRelationship instances
        """
        if not before_date:
            before_date = datetime.now()

        return self.db.query(PersonRelationship).filter(
            and_(
                PersonRelationship.executive_id == executive_id,
                PersonRelationship.next_follow_up <= before_date,
                PersonRelationship.next_follow_up.isnot(None)
            )
        ).order_by(
            PersonRelationship.next_follow_up.asc()
        ).all()

    def get_key_relationships(
        self,
        executive_id: int,
        min_strength: str = "strong"
    ) -> List[PersonRelationship]:
        """
        Get key relationships (strong or key strength).

        Args:
            executive_id: Executive ID
            min_strength: Minimum strength level ("strong" or "key")

        Returns:
            List of PersonRelationship instances
        """
        strengths = ["key"]
        if min_strength == "strong":
            strengths.append("strong")

        return self.db.query(PersonRelationship).filter(
            and_(
                PersonRelationship.executive_id == executive_id,
                PersonRelationship.relationship_strength.in_(strengths)
            )
        ).order_by(
            PersonRelationship.total_meetings.desc()
        ).all()

    def get_recent_relationships(
        self,
        executive_id: int,
        days: int = 30
    ) -> List[PersonRelationship]:
        """
        Get relationships with recent meetings.

        Args:
            executive_id: Executive ID
            days: Number of days to look back

        Returns:
            List of PersonRelationship instances
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        return self.db.query(PersonRelationship).filter(
            and_(
                PersonRelationship.executive_id == executive_id,
                PersonRelationship.last_met_date >= cutoff_date
            )
        ).order_by(
            PersonRelationship.last_met_date.desc()
        ).all()

    def search_relationships(
        self,
        executive_id: int,
        search_term: str
    ) -> List[PersonRelationship]:
        """
        Search relationships by name, email, or company.

        Args:
            executive_id: Executive ID
            search_term: Search term

        Returns:
            List of PersonRelationship instances
        """
        search_pattern = f"%{search_term}%"

        return self.db.query(PersonRelationship).filter(
            and_(
                PersonRelationship.executive_id == executive_id,
                or_(
                    PersonRelationship.person_name.like(search_pattern),
                    PersonRelationship.person_email.like(search_pattern),
                    PersonRelationship.person_company.like(search_pattern)
                )
            )
        ).all()
