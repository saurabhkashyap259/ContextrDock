"""Connector model placeholder for Phase 4."""

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class Connector(Base):
    """
    Connector represents a configured connection to a workplace tool.
    
    This is a placeholder for Phase 4 (US2).
    Will be fully implemented in T069-T070.
    """

    __tablename__ = "connectors"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    connector_definition_id = Column(
        Integer,
        ForeignKey("connector_definitions.id"),
        nullable=False,
        index=True
    )
    
    name = Column(String(255), nullable=False)  # User-defined name
    config_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    credentials_encrypted = Column(String(5000), nullable=True)  # Fernet encrypted
    sync_schedule = Column(String(100), nullable=True)  # Cron expression
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Connector(id={self.id}, name='{self.name}')>"
