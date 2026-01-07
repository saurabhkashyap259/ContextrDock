"""SQLAlchemy base model and database session management."""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import settings

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
)

# Create sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base: Any = declarative_base()

# Allow unmapped annotations for SQLAlchemy 2.0 compatibility
Base.__allow_unmapped__ = True


def get_db() -> Any:
    """Get database session dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
