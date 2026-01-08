"""Document model for storing indexed documents from connectors."""

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class Document(Base):
    """
    Document represents a single indexed item from a connector.

    Documents are the top-level objects that get chunked and embedded.
    Examples: Confluence page, Slack message, Jira issue, GitHub file.
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=True, index=True)

    # Source information
    source_type = Column(String(50), nullable=False, index=True)  # "confluence", "slack", "jira", etc.
    source_id = Column(String(500), nullable=False, index=True)  # External system's ID

    # Document metadata
    title = Column(String(1000), nullable=False)
    url = Column(String(2000), nullable=True)  # Deep link to original document
    content_hash = Column(String(64), nullable=True)  # SHA256 hash for change detection

    # JSONB field for connector-specific metadata
    # Example: {"space": "ENG", "author": "user@example.com", "labels": ["api", "docs"]}
    metadata_json = Column(JSONB, nullable=False, default=dict, server_default="{}")

    # Indexing timestamps
    last_indexed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    connector = relationship("Connector", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, source_type='{self.source_type}', title='{self.title[:50]}')>"
