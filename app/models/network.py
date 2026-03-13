"""
SQLAlchemy models mirroring Network Builder's database tables.

These do NOT create new tables — they map to NB's existing tables
so Calendar Notifier can read/write NB data via its shared DB connection.
"""

from sqlalchemy import Column, String, Integer, Float, Date, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

# Separate Base for NB models — these map to NB's existing tables
NetworkBase = declarative_base()


class NetworkPerson(NetworkBase):
    """Mirror of NB's 'people' table."""
    __tablename__ = 'people'

    id = Column(String, primary_key=True)
    person_id = Column(String, unique=True, nullable=False)  # Affinity person ID
    full_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    email_addresses = Column(String)  # Comma-separated
    primary_email = Column(String, index=True)
    last_email = Column(String)
    location_city = Column(String)
    location_state = Column(String)
    location_country = Column(String)
    industry = Column(String)
    linkedin_url = Column(String)
    last_contact = Column(Date)
    current_job_title = Column(String)
    # Graph metrics (computed by NB's graph_service)
    degree_centrality = Column(Float)
    betweenness_centrality = Column(Float)
    closeness_centrality = Column(Float)
    pagerank = Column(Float)
    cluster_id = Column(Integer)
    total_connections = Column(Integer)
    avg_relationship_strength = Column(Float)
    at_risk_connections = Column(Integer)


class NetworkRelationship(NetworkBase):
    """Mirror of NB's 'relationships' table."""
    __tablename__ = 'relationships'

    id = Column(String, primary_key=True)
    from_person_id = Column(String, ForeignKey('people.id'))
    to_person_id = Column(String, ForeignKey('people.id'))
    relationship_type = Column(String)
    strength = Column(Float)  # 0.0-1.0
    first_email_date = Column(DateTime)
    last_email_date = Column(DateTime)
    last_event_date = Column(DateTime)
    last_interaction_date = Column(DateTime)
    computed_decay_score = Column(Float)  # 0.0 (healthy) to 1.0 (fully decayed)
    updated_at = Column(DateTime)


class NetworkRelationshipSnapshot(NetworkBase):
    """Mirror of NB's 'relationship_snapshots' table."""
    __tablename__ = 'relationship_snapshots'

    id = Column(String, primary_key=True)
    relationship_id = Column(String, ForeignKey('relationships.id'))
    strength = Column(Float)
    recorded_at = Column(DateTime)
