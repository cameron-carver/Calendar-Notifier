"""
Second database connection to Network Builder's database.

Provides read/write access to NB's people, relationships, and snapshots tables.
Gracefully returns None if NETWORK_BUILDER_DATABASE_URL is not configured.
"""

import logging
from typing import Optional, Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger(__name__)

_network_engine = None
_NetworkSessionLocal = None


def _init_network_db():
    """Lazily initialize the Network Builder database connection."""
    global _network_engine, _NetworkSessionLocal

    if _NetworkSessionLocal is not None:
        return True

    if not settings.network_builder_database_url:
        logger.info("Network Builder integration disabled (NETWORK_BUILDER_DATABASE_URL not set)")
        return False

    try:
        connect_args = {}
        if "sqlite" in settings.network_builder_database_url:
            connect_args["check_same_thread"] = False

        _network_engine = create_engine(
            settings.network_builder_database_url,
            connect_args=connect_args,
        )
        _NetworkSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_network_engine
        )
        logger.info(f"Network Builder database connected: {settings.network_builder_database_url}")
        return True
    except Exception as e:
        logger.warning(f"Failed to connect to Network Builder database: {e}")
        return False


def get_network_db() -> Generator[Optional[Session], None, None]:
    """Dependency to get a Network Builder database session.

    Yields None if the NB database is not configured or unavailable.
    """
    if not _init_network_db() or _NetworkSessionLocal is None:
        yield None
        return

    db = _NetworkSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_network_session() -> Optional[Session]:
    """Get a standalone Network Builder session (non-dependency usage).

    Returns None if the NB database is not configured.
    Caller is responsible for closing the session.
    """
    if not _init_network_db() or _NetworkSessionLocal is None:
        return None
    return _NetworkSessionLocal()
