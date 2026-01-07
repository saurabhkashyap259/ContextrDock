"""Connector model for workplace tool integrations."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class Connector(Base):
    """
    Connector represents a configured connection to a workplace tool.
    
    Stores configuration, encrypted credentials, and sync state for each
    connected data source (Slack, Jira, Confluence, etc.).
    
    Attributes:
        workspace_id: Workspace this connector belongs to
        connector_definition_id: Type of connector (Slack, Jira, etc.)
        name: User-defined display name
        config_json: Connector-specific configuration (channels, projects, etc.)
        credentials_encrypted: Fernet-encrypted OAuth tokens or API keys
        sync_schedule: Cron expression for scheduled syncs (e.g., "0 */6 * * *")
        is_active: Whether connector is enabled for syncing
        last_synced_at: Timestamp of last successful sync
        cursor_state_json: Incremental sync state (cursors, timestamps)
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
    
    name = Column(String(255), nullable=False)
    config_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    credentials_encrypted = Column(LargeBinary, nullable=True)  # Fernet encrypted bytes
    sync_schedule = Column(String(100), nullable=True)  # Cron expression
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    cursor_state_json = Column(JSONB, nullable=True)  # For incremental sync
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Relationships
    workspace = relationship("Workspace", back_populates="connectors")
    connector_definition = relationship("ConnectorDefinition", back_populates="connectors")
    documents = relationship("Document", back_populates="connector", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="connector", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Connector(id={self.id}, name='{self.name}', active={self.is_active})>"
