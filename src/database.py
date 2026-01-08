"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from src.config.settings import settings

# Create database engine
# Connection pooling for performance (T203)
# - pool_size=20: Max permanent connections in pool
# - max_overflow=10: Max temporary connections beyond pool_size
# - pool_pre_ping=True: Verify connections before use (detects stale connections)
# - pool_recycle=3600: Recycle connections after 1 hour (prevents stale connections)
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    echo=settings.is_development,  # Log SQL in development
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for models
Base = declarative_base()


def get_db() -> Session:
    """Get database session.

    Yields:
        Database session

    Usage:
        db = next(get_db())
        try:
            # use db
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
