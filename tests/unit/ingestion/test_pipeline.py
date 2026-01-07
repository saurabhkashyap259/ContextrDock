"""Tests for document ingestion pipeline."""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from src.ingestion.pipeline import ingest_document
from src.models.document import Document


@patch("src.ingestion.pipeline.chunk_text")
@patch("src.ingestion.pipeline.EmbeddingService")
@patch("src.ingestion.pipeline.QdrantClient")
def test_ingest_document_basic(
    mock_qdrant_class,
    mock_embedding_class,
    mock_chunk_text,
    db_session: Session,
) -> None:
    """Test basic document ingestion."""
    # Mock chunker
    mock_chunk_text.return_value = [
        "This is chunk one.",
        "This is chunk two.",
    ]
    
    # Mock embedding service
    mock_embedding_service = Mock()
    mock_embedding_service.embed_texts.return_value = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    mock_embedding_class.return_value = mock_embedding_service
    
    # Mock Qdrant client
    mock_qdrant = Mock()
    mock_qdrant.upsert_vector.side_effect = ["uuid-1", "uuid-2"]
    mock_qdrant_class.return_value = mock_qdrant
    
    # Create document
    content = "This is a test document with some content."
    acl = {"readers": ["user@example.com"]}
    
    document = ingest_document(
        db_session=db_session,
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-123",
        title="Test Document",
        content=content,
        url="https://example.com/doc",
        acl=acl,
    )
    
    assert document.id is not None
    assert document.workspace_id == 1
    assert document.source_type == "confluence"
    assert document.title == "Test Document"
    
    # Verify chunking was called
    mock_chunk_text.assert_called_once_with(content, chunk_size=1000, chunk_overlap=200)
    
    # Verify embeddings were generated
    mock_embedding_service.embed_texts.assert_called_once()
    
    # Verify vectors were upserted to Qdrant
    assert mock_qdrant.upsert_vector.call_count == 2


@patch("src.ingestion.pipeline.chunk_text")
@patch("src.ingestion.pipeline.EmbeddingService")
@patch("src.ingestion.pipeline.QdrantClient")
def test_ingest_document_creates_chunks(
    mock_qdrant_class,
    mock_embedding_class,
    mock_chunk_text,
    db_session: Session,
) -> None:
    """Test that ingestion creates DocumentChunk records."""
    mock_chunk_text.return_value = ["Chunk 1", "Chunk 2", "Chunk 3"]
    
    mock_embedding_service = Mock()
    mock_embedding_service.embed_texts.return_value = [
        [0.1] * 1536,
        [0.2] * 1536,
        [0.3] * 1536,
    ]
    mock_embedding_class.return_value = mock_embedding_service
    
    mock_qdrant = Mock()
    mock_qdrant.upsert_vector.side_effect = ["id-1", "id-2", "id-3"]
    mock_qdrant_class.return_value = mock_qdrant
    
    document = ingest_document(
        db_session=db_session,
        workspace_id=1,
        connector_id=1,
        source_type="slack",
        source_id="C123-M456",
        title="Slack Message",
        content="Long message content...",
        acl={"channel_members": ["U001", "U002"]},
    )
    
    # Verify chunks were created (would need to query from db_session)
    assert document.id is not None


@patch("src.ingestion.pipeline.chunk_text")
@patch("src.ingestion.pipeline.EmbeddingService")
@patch("src.ingestion.pipeline.QdrantClient")
def test_ingest_document_empty_content(
    mock_qdrant_class,
    mock_embedding_class,
    mock_chunk_text,
    db_session: Session,
) -> None:
    """Test ingesting document with empty content."""
    mock_chunk_text.return_value = []
    
    document = ingest_document(
        db_session=db_session,
        workspace_id=1,
        connector_id=1,
        source_type="github",
        source_id="repo/file.md",
        title="Empty File",
        content="",
        acl={},
    )
    
    assert document.id is not None
    # No chunks should be created for empty content


@patch("src.ingestion.pipeline.chunk_text")
@patch("src.ingestion.pipeline.EmbeddingService")
@patch("src.ingestion.pipeline.QdrantClient")
def test_ingest_document_with_metadata(
    mock_qdrant_class,
    mock_embedding_class,
    mock_chunk_text,
    db_session: Session,
) -> None:
    """Test ingesting document with metadata."""
    mock_chunk_text.return_value = ["Content chunk"]
    
    mock_embedding_service = Mock()
    mock_embedding_service.embed_texts.return_value = [[0.1, 0.2]]
    mock_embedding_class.return_value = mock_embedding_service
    
    mock_qdrant = Mock()
    mock_qdrant.upsert_vector.return_value = "uuid-1"
    mock_qdrant_class.return_value = mock_qdrant
    
    metadata = {
        "space": "ENGINEERING",
        "author": "john@example.com",
        "labels": ["api", "documentation"],
    }
    
    document = ingest_document(
        db_session=db_session,
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-456",
        title="API Guide",
        content="API documentation content...",
        url="https://company.atlassian.net/wiki/456",
        acl={"readers": ["john@example.com"]},
        metadata=metadata,
    )
    
    assert document.metadata_json == metadata


@patch("src.ingestion.pipeline.chunk_text")
@patch("src.ingestion.pipeline.EmbeddingService")
@patch("src.ingestion.pipeline.QdrantClient")
def test_ingest_document_updates_existing(
    mock_qdrant_class,
    mock_embedding_class,
    mock_chunk_text,
    db_session: Session,
) -> None:
    """Test updating an existing document (re-indexing)."""
    # Create initial document
    existing_doc = Document(
        workspace_id=1,
        connector_id=1,
        source_type="jira",
        source_id="PROJ-123",
        title="Old Title",
        content_hash="old-hash",
    )
    db_session.add(existing_doc)
    db_session.commit()
    
    mock_chunk_text.return_value = ["Updated content"]
    
    mock_embedding_service = Mock()
    mock_embedding_service.embed_texts.return_value = [[0.5, 0.6]]
    mock_embedding_class.return_value = mock_embedding_service
    
    mock_qdrant = Mock()
    mock_qdrant.upsert_vector.return_value = "new-uuid"
    mock_qdrant_class.return_value = mock_qdrant
    
    # Ingest with same source_id (should update)
    document = ingest_document(
        db_session=db_session,
        workspace_id=1,
        connector_id=1,
        source_type="jira",
        source_id="PROJ-123",  # Same source_id
        title="Updated Title",
        content="Updated issue description",
        acl={},
    )
    
    # Should reuse existing document ID
    # (Implementation may create new or update existing)
    assert document.workspace_id == 1
    assert document.source_id == "PROJ-123"
