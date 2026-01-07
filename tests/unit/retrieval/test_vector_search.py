"""Tests for vector similarity search."""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from src.retrieval.vector_search import search_by_vector
from src.models.document import Document
from src.models.document_chunk import DocumentChunk


@patch("src.retrieval.vector_search.EmbeddingService")
@patch("src.retrieval.vector_search.QdrantClient")
def test_search_by_vector_basic(
    mock_qdrant_class,
    mock_embedding_class,
    db_session: Session,
) -> None:
    """Test basic vector similarity search."""
    # Mock embedding service
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]
    mock_embedding_class.return_value = mock_embedding_service
    
    # Mock Qdrant results
    mock_qdrant = Mock()
    mock_qdrant.search_vectors.return_value = [
        {
            "id": "uuid-1",
            "score": 0.95,
            "metadata": {
                "chunk_id": 1,
                "document_id": 1,
                "workspace_id": 1,
                "title": "API Guide",
                "url": "https://example.com/api",
                "source_type": "confluence",
            }
        }
    ]
    mock_qdrant_class.return_value = mock_qdrant
    
    # Create test data
    doc = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-1",
        title="API Guide",
        url="https://example.com/api",
    )
    db_session.add(doc)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="OAuth 2.0 authentication guide",
        token_count=5,
        embedding_id="uuid-1",
        acl_json={"readers": ["user@example.com"]},
    )
    db_session.add(chunk)
    db_session.commit()
    
    # Search
    results = search_by_vector(
        db_session=db_session,
        query="How do I authenticate?",
        workspace_id=1,
        top_k=5,
    )
    
    assert len(results) > 0
    assert results[0]["score"] == 0.95
    assert results[0]["title"] == "API Guide"
    
    # Verify embedding was generated
    mock_embedding_service.embed_text.assert_called_once_with("How do I authenticate?")
    
    # Verify Qdrant was queried
    mock_qdrant.search_vectors.assert_called_once()


@patch("src.retrieval.vector_search.EmbeddingService")
@patch("src.retrieval.vector_search.QdrantClient")
def test_search_by_vector_with_filters(
    mock_qdrant_class,
    mock_embedding_class,
    db_session: Session,
) -> None:
    """Test vector search with workspace filtering."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text.return_value = [0.1] * 1536
    mock_embedding_class.return_value = mock_embedding_service
    
    mock_qdrant = Mock()
    mock_qdrant.search_vectors.return_value = []
    mock_qdrant_class.return_value = mock_qdrant
    
    search_by_vector(db_session, "test query", workspace_id=1, top_k=10)
    
    # Check that workspace filter was passed to Qdrant
    call_args = mock_qdrant.search_vectors.call_args
    assert call_args[1]["filters"]["workspace_id"] == 1


@patch("src.retrieval.vector_search.EmbeddingService")
@patch("src.retrieval.vector_search.QdrantClient")
def test_search_by_vector_empty_query(
    mock_qdrant_class,
    mock_embedding_class,
    db_session: Session,
) -> None:
    """Test vector search with empty query."""
    results = search_by_vector(db_session, "", workspace_id=1, top_k=10)
    
    assert results == []


@patch("src.retrieval.vector_search.EmbeddingService")
@patch("src.retrieval.vector_search.QdrantClient")
def test_search_by_vector_enriches_with_chunk_data(
    mock_qdrant_class,
    mock_embedding_class,
    db_session: Session,
) -> None:
    """Test that vector search enriches results with chunk data from database."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text.return_value = [0.1, 0.2]
    mock_embedding_class.return_value = mock_embedding_service
    
    # Qdrant returns minimal metadata
    mock_qdrant = Mock()
    mock_qdrant.search_vectors.return_value = [
        {
            "id": "uuid-1",
            "score": 0.88,
            "metadata": {"chunk_id": 1, "workspace_id": 1},
        }
    ]
    mock_qdrant_class.return_value = mock_qdrant
    
    # Create database records
    doc = Document(
        workspace_id=1,
        connector_id=1,
        source_type="slack",
        source_id="C123-M456",
        title="Team Discussion",
        url="https://slack.com/archives/C123/p456",
    )
    db_session.add(doc)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Discussion about the new feature",
        token_count=6,
        embedding_id="uuid-1",
        acl_json={"channel_members": ["U001", "U002"]},
    )
    db_session.add(chunk)
    db_session.commit()
    
    results = search_by_vector(db_session, "new feature", workspace_id=1, top_k=5)
    
    assert len(results) == 1
    assert results[0]["content"] == "Discussion about the new feature"
    assert results[0]["acl"]["channel_members"] == ["U001", "U002"]


@patch("src.retrieval.vector_search.EmbeddingService")
@patch("src.retrieval.vector_search.QdrantClient")
def test_search_by_vector_top_k_limit(
    mock_qdrant_class,
    mock_embedding_class,
    db_session: Session,
) -> None:
    """Test that top_k parameter is passed to Qdrant."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text.return_value = [0.1] * 1536
    mock_embedding_class.return_value = mock_embedding_service
    
    mock_qdrant = Mock()
    mock_qdrant.search_vectors.return_value = []
    mock_qdrant_class.return_value = mock_qdrant
    
    search_by_vector(db_session, "query", workspace_id=1, top_k=20)
    
    call_args = mock_qdrant.search_vectors.call_args
    assert call_args[1]["top_k"] == 20
