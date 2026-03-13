"""
Service for managing meeting annotations in EA mode.

Handles EA-added context, notes, priorities, and follow-up tracking
for executive meetings.
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.brief import MeetingAnnotation


class AnnotationService:
    """Service for meeting annotation management."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_annotation(
        self,
        executive_id: int,
        event_id: str,
        priority: str = "normal",
        **kwargs
    ) -> MeetingAnnotation:
        """
        Create or update annotation for a meeting.

        If an annotation already exists for this executive + event,
        it will be updated instead.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID
            priority: Priority level ("critical" | "high" | "normal" | "low")
            **kwargs: Optional fields (prep_notes, action_before_meeting, etc.)

        Returns:
            MeetingAnnotation instance
        """
        # Check if annotation exists
        existing = self.get_annotation(executive_id, event_id)

        if existing:
            # Update existing annotation
            return self.update_annotation(
                existing.id,
                priority=priority,
                **kwargs
            )

        # Create new annotation
        annotation = MeetingAnnotation(
            executive_id=executive_id,
            event_id=event_id,
            priority=priority,
            **kwargs
        )

        self.db.add(annotation)
        self.db.commit()
        self.db.refresh(annotation)

        return annotation

    def get_annotation(
        self,
        executive_id: int,
        event_id: str
    ) -> Optional[MeetingAnnotation]:
        """
        Get annotation for a specific meeting.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID

        Returns:
            MeetingAnnotation instance or None if not found
        """
        return self.db.query(MeetingAnnotation).filter(
            and_(
                MeetingAnnotation.executive_id == executive_id,
                MeetingAnnotation.event_id == event_id
            )
        ).first()

    def get_annotation_by_id(
        self,
        annotation_id: int
    ) -> Optional[MeetingAnnotation]:
        """
        Get annotation by ID.

        Args:
            annotation_id: Annotation ID

        Returns:
            MeetingAnnotation instance or None if not found
        """
        return self.db.query(MeetingAnnotation).filter(
            MeetingAnnotation.id == annotation_id
        ).first()

    def list_annotations(
        self,
        executive_id: int,
        priority: Optional[str] = None,
        has_follow_up: Optional[bool] = None
    ) -> List[MeetingAnnotation]:
        """
        List annotations for an executive.

        Args:
            executive_id: Executive ID
            priority: Filter by priority level
            has_follow_up: If True, only return annotations with follow-up required

        Returns:
            List of MeetingAnnotation instances
        """
        query = self.db.query(MeetingAnnotation).filter(
            MeetingAnnotation.executive_id == executive_id
        )

        if priority:
            query = query.filter(MeetingAnnotation.priority == priority)

        if has_follow_up is not None:
            query = query.filter(
                MeetingAnnotation.follow_up_required == has_follow_up
            )

        return query.order_by(
            MeetingAnnotation.created_at.desc()
        ).all()

    def update_annotation(
        self,
        annotation_id: int,
        **updates
    ) -> Optional[MeetingAnnotation]:
        """
        Update annotation fields.

        Args:
            annotation_id: Annotation ID
            **updates: Fields to update

        Returns:
            Updated MeetingAnnotation instance or None if not found
        """
        annotation = self.get_annotation_by_id(annotation_id)

        if not annotation:
            return None

        # Update fields
        for field, value in updates.items():
            if hasattr(annotation, field):
                setattr(annotation, field, value)

        self.db.commit()
        self.db.refresh(annotation)

        return annotation

    def delete_annotation(self, annotation_id: int) -> bool:
        """
        Delete annotation.

        Args:
            annotation_id: Annotation ID

        Returns:
            True if deleted, False if not found
        """
        annotation = self.get_annotation_by_id(annotation_id)

        if not annotation:
            return False

        self.db.delete(annotation)
        self.db.commit()

        return True

    def set_priority(
        self,
        executive_id: int,
        event_id: str,
        priority: str
    ) -> Optional[MeetingAnnotation]:
        """
        Set priority for a meeting.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID
            priority: Priority level ("critical" | "high" | "normal" | "low")

        Returns:
            Updated or created MeetingAnnotation instance
        """
        annotation = self.get_annotation(executive_id, event_id)

        if annotation:
            annotation.priority = priority
            self.db.commit()
            self.db.refresh(annotation)
            return annotation

        # Create new annotation with priority
        return self.create_annotation(
            executive_id=executive_id,
            event_id=event_id,
            priority=priority
        )

    def add_prep_notes(
        self,
        executive_id: int,
        event_id: str,
        prep_notes: str,
        action_before: Optional[str] = None
    ) -> Optional[MeetingAnnotation]:
        """
        Add preparation notes for a meeting.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID
            prep_notes: Context and preparation notes
            action_before: Actions to take before meeting

        Returns:
            Updated or created MeetingAnnotation instance
        """
        annotation = self.get_annotation(executive_id, event_id)

        if annotation:
            annotation.prep_notes = prep_notes
            if action_before:
                annotation.action_before_meeting = action_before
            self.db.commit()
            self.db.refresh(annotation)
            return annotation

        # Create new annotation
        return self.create_annotation(
            executive_id=executive_id,
            event_id=event_id,
            prep_notes=prep_notes,
            action_before_meeting=action_before
        )

    def add_post_meeting_notes(
        self,
        executive_id: int,
        event_id: str,
        post_notes: str,
        decisions: Optional[str] = None,
        action_items: Optional[List[dict]] = None
    ) -> Optional[MeetingAnnotation]:
        """
        Add post-meeting notes and outcomes.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID
            post_notes: Post-meeting notes
            decisions: Decisions made during meeting
            action_items: List of action items with owners

        Returns:
            Updated or created MeetingAnnotation instance
        """
        annotation = self.get_annotation(executive_id, event_id)

        if annotation:
            annotation.post_meeting_notes = post_notes
            if decisions:
                annotation.decisions_made = decisions
            if action_items:
                annotation.action_items = action_items
            self.db.commit()
            self.db.refresh(annotation)
            return annotation

        # Create new annotation
        return self.create_annotation(
            executive_id=executive_id,
            event_id=event_id,
            post_meeting_notes=post_notes,
            decisions_made=decisions,
            action_items=action_items
        )

    def set_follow_up(
        self,
        executive_id: int,
        event_id: str,
        follow_up_date: datetime,
        follow_up_notes: Optional[str] = None
    ) -> Optional[MeetingAnnotation]:
        """
        Set follow-up reminder for a meeting.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID
            follow_up_date: When to follow up
            follow_up_notes: Follow-up context

        Returns:
            Updated or created MeetingAnnotation instance
        """
        annotation = self.get_annotation(executive_id, event_id)

        if annotation:
            annotation.follow_up_required = True
            annotation.follow_up_date = follow_up_date
            if follow_up_notes:
                annotation.follow_up_notes = follow_up_notes
            self.db.commit()
            self.db.refresh(annotation)
            return annotation

        # Create new annotation
        return self.create_annotation(
            executive_id=executive_id,
            event_id=event_id,
            follow_up_required=True,
            follow_up_date=follow_up_date,
            follow_up_notes=follow_up_notes
        )

    def clear_follow_up(
        self,
        executive_id: int,
        event_id: str
    ) -> Optional[MeetingAnnotation]:
        """
        Clear follow-up requirement for a meeting.

        Args:
            executive_id: Executive ID
            event_id: Google Calendar event ID

        Returns:
            Updated MeetingAnnotation instance or None if not found
        """
        annotation = self.get_annotation(executive_id, event_id)

        if annotation:
            annotation.follow_up_required = False
            annotation.follow_up_date = None
            self.db.commit()
            self.db.refresh(annotation)

        return annotation

    def get_upcoming_follow_ups(
        self,
        executive_id: int,
        before_date: Optional[datetime] = None
    ) -> List[MeetingAnnotation]:
        """
        Get all meetings requiring follow-up.

        Args:
            executive_id: Executive ID
            before_date: Optional date filter (get follow-ups before this date)

        Returns:
            List of MeetingAnnotation instances with follow-ups
        """
        query = self.db.query(MeetingAnnotation).filter(
            and_(
                MeetingAnnotation.executive_id == executive_id,
                MeetingAnnotation.follow_up_required == True
            )
        )

        if before_date:
            query = query.filter(
                MeetingAnnotation.follow_up_date <= before_date
            )

        return query.order_by(
            MeetingAnnotation.follow_up_date.asc()
        ).all()

    def get_priority_meetings(
        self,
        executive_id: int,
        priority_levels: Optional[List[str]] = None
    ) -> List[MeetingAnnotation]:
        """
        Get high-priority meetings.

        Args:
            executive_id: Executive ID
            priority_levels: List of priority levels to include
                           Default: ["critical", "high"]

        Returns:
            List of MeetingAnnotation instances
        """
        if not priority_levels:
            priority_levels = ["critical", "high"]

        return self.db.query(MeetingAnnotation).filter(
            and_(
                MeetingAnnotation.executive_id == executive_id,
                MeetingAnnotation.priority.in_(priority_levels)
            )
        ).order_by(
            MeetingAnnotation.created_at.desc()
        ).all()

    def bulk_set_priority(
        self,
        annotations: List[tuple],
        priority: str
    ) -> int:
        """
        Set priority for multiple meetings at once.

        Args:
            annotations: List of (executive_id, event_id) tuples
            priority: Priority level to set

        Returns:
            Number of annotations updated
        """
        count = 0

        for executive_id, event_id in annotations:
            annotation = self.set_priority(executive_id, event_id, priority)
            if annotation:
                count += 1

        return count
