"""SyncRun model for tracking connector sync operations."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class SyncRun(Base):
    """
    SyncRun tracks individual sync operations for connectors.
    
    Each time a connector syncs (either scheduled or manual), a SyncRun
    record is created to track progress, status, and results.
    
    Attributes:
        connector_id: The connector being synced
        status: Current status (running, completed, failed, cancelled)
        started_at: When sync began
        completed_at: When sync finished (success or failure)
        documents_added: Count of new documents indexed
        documents_updated: Count of existing documents updated
        documents_deleted: Count of documents removed
        error_message: Error details if sync failed
        cursor_state_json: State for resuming/incremental sync
    """

    __tablename__ = "sync_runs"

    id = Column(Integer, primary_key=True, index=True)
    connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=False, index=True)
    
    # Sync status and timing
    status = Column(
        String(50),
        nullable=False,
        index=True,
    )  # "running", "completed", "failed", "cancelled"
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Sync results
    documents_added = Column(Integer, nullable=False, default=0, server_default="0")
    documents_updated = Column(Integer, nullable=False, default=0, server_default="0")
    documents_deleted = Column(Integer, nullable=False, default=0, server_default="0")
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    
    # Incremental sync state
    # Example: {"next_page_token": "abc123", "last_message_ts": "1234567890.123456"}
    cursor_state_json = Column(JSONB, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    connector = relationship("Connector", back_populates="sync_runs")

    def __repr__(self) -> str:
        return f"<SyncRun(id={self.id}, connector_id={self.connector_id}, status='{self.status}')>"
