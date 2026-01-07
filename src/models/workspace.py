"""Workspace model for multi-tenancy support."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.base import Base


class Workspace(Base):
    """Workspace represents a logical container for a team's data.
    
    This enables future multi-tenancy support where each organization
    has its own isolated workspace with separate users, connectors, and documents.
    """

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Relationships
    connectors = relationship("Connector", back_populates="workspace")

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, name='{self.name}')>"
