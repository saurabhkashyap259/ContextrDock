"""ConnectorDefinition model for storing connector metadata."""

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class ConnectorDefinition(Base):
    """
    Defines metadata for connector types (Slack, Jira, GitHub, etc.).
    
    This table stores the definition of each connector type, including:
    - Configuration schema (JSON Schema format)
    - OAuth scopes required for authentication
    - Supported operations (read/write capabilities)
    - Versioning information
    
    Example:
        Slack connector definition with read capabilities and required scopes
    """

    __tablename__ = "connector_definitions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # Display name (e.g., "Slack")
    connector_type = Column(String(100), nullable=False, unique=True, index=True)  # System identifier (e.g., "slack")
    description = Column(String(1000), nullable=True)  # Human-readable description
    
    # JSON Schema defining required configuration fields
    config_schema = Column(JSONB, nullable=False, default=dict, server_default="{}")
    
    # OAuth scopes required for this connector
    oauth_scopes = Column(JSONB, nullable=False, default=list, server_default="[]")
    
    # Connector capabilities
    supports_read = Column(Boolean, nullable=False, default=True)
    supports_write = Column(Boolean, nullable=False, default=False)
    
    # Version tracking for connector definition changes
    version = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Relationships
    connectors = relationship("Connector", back_populates="connector_definition")

    def __repr__(self) -> str:
        return f"<ConnectorDefinition(id={self.id}, name='{self.name}', type='{self.connector_type}')>"
