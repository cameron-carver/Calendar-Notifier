"""
Network Context Service — reads graph analytics from Network Builder's database.

Direction: NB → CN (Network Builder provides context to Calendar Notifier)

Provides person-level graph metrics (PageRank, centrality, cluster),
relationship context (strength, decay), and connection pathfinding
for use in morning brief enrichment.
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.network import NetworkPerson, NetworkRelationship

logger = logging.getLogger(__name__)


# Strength float ↔ label mapping
STRENGTH_THRESHOLDS = [
    (0.8, "key"),
    (0.5, "strong"),
    (0.2, "developing"),
    (0.0, "new"),
]

LABEL_TO_FLOAT = {
    "new": 0.1,
    "developing": 0.35,
    "strong": 0.65,
    "key": 0.9,
}


class NetworkContextService:
    """Reads Network Builder graph analytics for brief enrichment."""

    def __init__(self, network_db: Optional[Session]):
        """
        Args:
            network_db: SQLAlchemy session to NB's database. None if NB is not configured.
        """
        self.db = network_db
        self.enabled = network_db is not None

    def get_person_context(self, email: str) -> Optional[Dict[str, Any]]:
        """Look up a person in NB by email and return their graph metrics.

        Returns None if person not found or NB is not connected.
        """
        if not self.enabled:
            return None

        try:
            person = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.primary_email == email.lower())
                .first()
            )

            if not person:
                # Try searching in comma-separated email_addresses
                person = (
                    self.db.query(NetworkPerson)
                    .filter(NetworkPerson.email_addresses.contains(email.lower()))
                    .first()
                )

            if not person:
                return None

            return {
                "nb_person_id": person.id,
                "full_name": person.full_name,
                "pagerank": person.pagerank,
                "degree_centrality": person.degree_centrality,
                "betweenness_centrality": person.betweenness_centrality,
                "closeness_centrality": person.closeness_centrality,
                "cluster_id": person.cluster_id,
                "total_connections": person.total_connections,
                "avg_relationship_strength": person.avg_relationship_strength,
                "at_risk_connections": person.at_risk_connections,
                "network_strength_label": self.get_network_strength_label(
                    person.avg_relationship_strength
                ),
            }
        except Exception as e:
            logger.warning(f"Failed to get NB person context for {email}: {e}")
            return None

    def get_relationship_context(
        self, email_a: str, email_b: str
    ) -> Optional[Dict[str, Any]]:
        """Get the relationship edge between two people by email.

        Returns None if no relationship found or NB is not connected.
        """
        if not self.enabled:
            return None

        try:
            person_a = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.primary_email == email_a.lower())
                .first()
            )
            person_b = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.primary_email == email_b.lower())
                .first()
            )

            if not person_a or not person_b:
                return None

            # Relationships are stored with normalized pair ordering
            rel = (
                self.db.query(NetworkRelationship)
                .filter(
                    or_(
                        (NetworkRelationship.from_person_id == person_a.id)
                        & (NetworkRelationship.to_person_id == person_b.id),
                        (NetworkRelationship.from_person_id == person_b.id)
                        & (NetworkRelationship.to_person_id == person_a.id),
                    )
                )
                .first()
            )

            if not rel:
                return None

            return {
                "strength": rel.strength,
                "computed_decay_score": rel.computed_decay_score,
                "last_interaction_date": rel.last_interaction_date,
                "last_email_date": rel.last_email_date,
                "last_event_date": rel.last_event_date,
                "relationship_type": rel.relationship_type,
                "strength_label": self.get_network_strength_label(rel.strength),
            }
        except Exception as e:
            logger.warning(f"Failed to get NB relationship context: {e}")
            return None

    def find_connection_path(
        self, email_a: str, email_b: str
    ) -> Optional[List[str]]:
        """Find the shortest path between two people via NB's HTTP API.

        Falls back to None if NB backend is not running.
        """
        if not self.enabled:
            return None

        try:
            # Look up person IDs by email
            person_a = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.primary_email == email_a.lower())
                .first()
            )
            person_b = (
                self.db.query(NetworkPerson)
                .filter(NetworkPerson.primary_email == email_b.lower())
                .first()
            )

            if not person_a or not person_b:
                return None

            # Call NB's API for pathfinding (requires NB backend running)
            import httpx

            response = httpx.get(
                f"http://localhost:8000/network/path/{person_a.id}/{person_b.id}",
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                return [node["name"] for node in data.get("path", [])]
            return None
        except Exception as e:
            logger.debug(f"Path lookup failed (NB backend may not be running): {e}")
            return None

    @staticmethod
    def get_network_strength_label(strength: Optional[float]) -> Optional[str]:
        """Map NB's 0.0-1.0 float strength to CN's enum label."""
        if strength is None:
            return None
        for threshold, label in STRENGTH_THRESHOLDS:
            if strength >= threshold:
                return label
        return "new"

    @staticmethod
    def get_float_from_label(label: str) -> float:
        """Map CN's strength label to NB's float value."""
        return LABEL_TO_FLOAT.get(label, 0.1)
