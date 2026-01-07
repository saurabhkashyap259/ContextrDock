"""Tests for DocumentChunk model."""

import pytest
from sqlalchemy.orm import Session

from src.models.document import Document
from src.models.document_chunk import DocumentChunk


def test_document_chunk_creation(db_session: Session) -> None:
    """Test creating a document chunk."""
    # Create parent document first
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-123",
        title="API Guide",
    )
    db_session.add(document)
    db_session.commit()
    
    # Create chunk
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="This is the introduction section of the API documentation...",
        token_count=150,
        embedding_id="qdrant-uuid-123",
        acl_json={"readers": ["user@example.com"], "groups": ["engineers"]},
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    assert chunk.id is not None
    assert chunk.document_id == document.id
    assert chunk.chunk_index == 0
    assert "introduction" in chunk.content
    assert chunk.token_count == 150
    assert chunk.embedding_id == "qdrant-uuid-123"
    assert "user@example.com" in chunk.acl_json["readers"]
    assert chunk.created_at is not None


def test_document_chunk_required_fields(db_session: Session) -> None:
    """Test that required fields are enforced."""
    chunk = DocumentChunk(
        chunk_index=0,
        content="Some content",
    )
    db_session.add(chunk)
    
    with pytest.raises(Exception):  # Will raise IntegrityError (missing document_id)
        db_session.commit()


def test_document_chunk_ordering(db_session: Session) -> None:
    """Test that chunks maintain order via chunk_index."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="github",
        source_id="repo/README.md",
        title="README",
    )
    db_session.add(document)
    db_session.commit()
    
    # Create chunks in order
    chunk1 = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="First paragraph...",
        token_count=100,
    )
    chunk2 = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Second paragraph...",
        token_count=120,
    )
    chunk3 = DocumentChunk(
        document_id=document.id,
        chunk_index=2,
        content="Third paragraph...",
        token_count=90,
    )
    db_session.add_all([chunk1, chunk2, chunk3])
    db_session.commit()
    
    # Query chunks in order
    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document.id
    ).order_by(DocumentChunk.chunk_index).all()
    
    assert len(chunks) == 3
    assert chunks[0].content.startswith("First")
    assert chunks[1].content.startswith("Second")
    assert chunks[2].content.startswith("Third")


def test_document_chunk_acl_json(db_session: Session) -> None:
    """Test that ACL is stored as JSONB."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="slack",
        source_id="C123-M456",
        title="Message",
    )
    db_session.add(document)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Team discussion about project...",
        token_count=80,
        acl_json={
            "channel_id": "C123",
            "channel_type": "private",
            "members": ["U001", "U002", "U003"],
        },
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    
    assert chunk.acl_json["channel_id"] == "C123"
    assert chunk.acl_json["channel_type"] == "private"
    assert len(chunk.acl_json["members"]) == 3


def test_document_chunk_embedding_id_nullable(db_session: Session) -> None:
    """Test that embedding_id is optional (may be populated later)."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="jira",
        source_id="PROJ-123",
        title="Issue",
    )
    db_session.add(document)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Issue description...",
        token_count=50,
        embedding_id=None,  # Not yet embedded
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    
    assert chunk.embedding_id is None
    
    # Later, update with embedding ID
    chunk.embedding_id = "qdrant-uuid-456"
    db_session.commit()
    db_session.refresh(chunk)
    
    assert chunk.embedding_id == "qdrant-uuid-456"
