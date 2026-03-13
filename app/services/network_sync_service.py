"""
Network Sync Service — pushes meeting data from Calendar Notifier into Network Builder.

Direction: CN → NB (Calendar feeds the network graph)

When Calendar Notifier generates a morning brief, it records meeting interactions
in NB's database so the graph stays fresh with interaction timestamps.
This feeds NB's decay model and surfaces co-attendance relationships.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.network import NetworkPerson, NetworkRelationship

logger = logging.getLogger(__name__)


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class NetworkSyncService:
    """Pushes meeting interaction data into Network Builder's database."""

    def __init__(self, network_db: Optional[Session]):
        """
        Args:
            network_db: SQLAlchemy session to NB's database. None if NB is not configured.
        """
        self.db = network_db
        self.enabled = network_db is not None

    def record_meeting_interaction(
        self,
        executive_email: str,
        attendee_emails: List[str],
        meeting_date: datetime,
        meeting_title: Optional[str] = None,
    ) -> int:
        """Record meeting interactions between executive and each attendee in NB.

        For each exec ↔ attendee pair:
        - If relationship exists: update last_interaction_date and last_event_date
        - If relationship doesn't exist but both people are in NB: create new edge

        Returns the number of relationships updated/created.
        """
        if not self.enabled:
            return 0

        try:
            # Look up executive in NB
            exec_person = self._find_person_by_email(executive_email)
            if not exec_person:
                return 0

            count = 0
            for attendee_email in attendee_emails:
                if attendee_email.lower() == executive_email.lower():
                    continue

                attendee_person = self._find_person_by_email(attendee_email)
                if not attendee_person:
                    continue

                updated = self._upsert_interaction(
                    exec_person.id, attendee_person.id, meeting_date
                )
                if updated:
                    count += 1

            if count > 0:
                self.db.commit()
                logger.info(
                    f"Recorded {count} meeting interactions for {meeting_title or 'meeting'}"
                )

            return count
        except Exception as e:
            logger.warning(f"Failed to record meeting interactions: {e}")
            self.db.rollback()
            return 0

    def record_co_attendance(
        self,
        attendee_emails: List[str],
        meeting_date: datetime,
    ) -> int:
        """Create/update weak-tie relationships between co-attendees.

        For each pair of external attendees in the same meeting,
        creates a relationship edge with low strength (0.05).

        Returns the number of co-attendance edges created/updated.
        """
        if not self.enabled or len(attendee_emails) < 2:
            return 0

        try:
            # Resolve all emails to NB person IDs
            email_to_person = {}
            for email in attendee_emails:
                person = self._find_person_by_email(email)
                if person:
                    email_to_person[email.lower()] = person

            if len(email_to_person) < 2:
                return 0

            # Create edges for all pairs
            persons = list(email_to_person.values())
            count = 0
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    updated = self._upsert_interaction(
                        persons[i].id,
                        persons[j].id,
                        meeting_date,
                        default_strength=0.05,
                        relationship_type="co-attendance",
                    )
                    if updated:
                        count += 1

            if count > 0:
                self.db.commit()
                logger.info(f"Recorded {count} co-attendance edges")

            return count
        except Exception as e:
            logger.warning(f"Failed to record co-attendance: {e}")
            self.db.rollback()
            return 0

    def backfill_person_data(
        self,
        person_email: str,
        name: Optional[str] = None,
        company: Optional[str] = None,
        linkedin_url: Optional[str] = None,
    ) -> bool:
        """Fill in missing person data in NB from CN's richer attendee info.

        Only updates fields that are currently empty in NB.
        Returns True if any fields were updated.
        """
        if not self.enabled:
            return False

        try:
            person = self._find_person_by_email(person_email)
            if not person:
                return False

            updated = False
            if name and not person.full_name:
                parts = name.split(" ", 1)
                person.full_name = name
                person.first_name = parts[0]
                person.last_name = parts[1] if len(parts) > 1 else ""
                updated = True

            if linkedin_url and not person.linkedin_url:
                person.linkedin_url = linkedin_url
                updated = True

            if updated:
                self.db.commit()
                logger.debug(f"Backfilled person data for {person_email}")

            return updated
        except Exception as e:
            logger.warning(f"Failed to backfill person data for {person_email}: {e}")
            self.db.rollback()
            return False

    def sync_strength_to_nb(
        self,
        executive_email: str,
        person_email: str,
        cn_strength_label: str,
    ) -> bool:
        """Push CN's human-labeled relationship strength to NB.

        Maps CN's enum label to NB's float and updates the relationship.
        """
        if not self.enabled:
            return False

        from app.services.network_context_service import NetworkContextService

        try:
            exec_person = self._find_person_by_email(executive_email)
            person = self._find_person_by_email(person_email)
            if not exec_person or not person:
                return False

            float_strength = NetworkContextService.get_float_from_label(cn_strength_label)

            rel = self._find_relationship(exec_person.id, person.id)
            if rel:
                rel.strength = float_strength
                rel.updated_at = datetime.utcnow()
                self.db.commit()
                logger.info(
                    f"Synced strength to NB: {person_email} = {cn_strength_label} ({float_strength})"
                )
                return True

            return False
        except Exception as e:
            logger.warning(f"Failed to sync strength to NB: {e}")
            self.db.rollback()
            return False

    def _find_person_by_email(self, email: str) -> Optional[NetworkPerson]:
        """Look up a person in NB by email."""
        person = (
            self.db.query(NetworkPerson)
            .filter(NetworkPerson.primary_email == email.lower())
            .first()
        )
        if not person:
            # Fallback: search comma-separated email_addresses
            person = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.email_addresses.contains(email.lower()))
                .first()
            )
        return person

    def _find_relationship(
        self, person_id_a: str, person_id_b: str
    ) -> Optional[NetworkRelationship]:
        """Find the relationship edge between two NB people (either direction)."""
        pair = tuple(sorted([person_id_a, person_id_b]))
        return (
            self.db.query(NetworkRelationship)
            .filter(
                or_(
                    (NetworkRelationship.from_person_id == pair[0])
                    & (NetworkRelationship.to_person_id == pair[1]),
                    (NetworkRelationship.from_person_id == pair[1])
                    & (NetworkRelationship.to_person_id == pair[0]),
                )
            )
            .first()
        )

    def _upsert_interaction(
        self,
        person_id_a: str,
        person_id_b: str,
        meeting_date: datetime,
        default_strength: float = 0.1,
        relationship_type: str = "meeting",
    ) -> bool:
        """Create or update a relationship edge with interaction timestamp.

        Returns True if a change was made.
        """
        pair = tuple(sorted([person_id_a, person_id_b]))
        rel = self._find_relationship(pair[0], pair[1])

        if rel:
            # Update interaction timestamps
            if rel.last_interaction_date is None or meeting_date > rel.last_interaction_date:
                rel.last_interaction_date = meeting_date
                rel.last_event_date = meeting_date
                rel.updated_at = datetime.utcnow()
            return True
        else:
            # Create new relationship edge
            new_rel = NetworkRelationship(
                id=_gen_uuid(),
                from_person_id=pair[0],
                to_person_id=pair[1],
                relationship_type=relationship_type,
                strength=default_strength,
                last_event_date=meeting_date,
                last_interaction_date=meeting_date,
                updated_at=datetime.utcnow(),
            )
            self.db.add(new_rel)
            return True
