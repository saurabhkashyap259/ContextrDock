"""DocumentChunk model for storing chunked and embedded content."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class DocumentChunk(Base):
    """
    DocumentChunk represents a chunked piece of a document with embeddings.

    Documents are split into chunks (500-1000 tokens) for embedding and retrieval.
    Each chunk includes ACL information for permission-aware filtering.
    """

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chunk ordering and content
    chunk_index = Column(Integer, nullable=False)  # 0-based index within document
    content = Column(Text, nullable=False)  # The actual text content
    token_count = Column(Integer, nullable=False)  # Number of tokens in chunk

    # Vector database reference
    embedding_id = Column(String(500), nullable=True, index=True)  # UUID in Qdrant/Weaviate

    # ACL information for permission-aware retrieval
    # Example: {"readers": ["user@example.com"], "groups": ["team-eng"], "visibility": "public"}
    acl_json = Column(JSONB, nullable=False, default=dict, server_default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"
