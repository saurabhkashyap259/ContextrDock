"""Tests for BM25 keyword search using PostgreSQL full-text search."""

import pytest
from sqlalchemy.orm import Session

from src.retrieval.keyword_search import search_by_keywords
from src.models.document import Document
from src.models.document_chunk import DocumentChunk


def test_search_by_keywords_basic(db_session: Session) -> None:
    """Test basic keyword search."""
    # Create test documents
    doc1 = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-1",
        title="API Authentication Guide",
    )
    doc2 = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-2",
        title="Database Setup",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()
    
    # Create chunks
    chunk1 = DocumentChunk(
        document_id=doc1.id,
        chunk_index=0,
        content="Our API uses OAuth 2.0 for authentication and authorization.",
        token_count=10,
    )
    chunk2 = DocumentChunk(
        document_id=doc2.id,
        chunk_index=0,
        content="To set up the PostgreSQL database, run the migration scripts.",
        token_count=12,
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()
    
    # Search for "authentication"
    results = search_by_keywords(
        db_session=db_session,
        query="authentication",
        workspace_id=1,
        top_k=10,
    )
    
    assert len(results) > 0
    # First result should be the authentication document
    assert "authentication" in results[0]["content"].lower()


def test_search_by_keywords_workspace_filter(db_session: Session) -> None:
    """Test that search filters by workspace."""
    # Create documents in different workspaces
    doc1 = Document(workspace_id=1, connector_id=1, source_type="slack", source_id="1", title="Doc 1")
    doc2 = Document(workspace_id=2, connector_id=1, source_type="slack", source_id="2", title="Doc 2")
    db_session.add_all([doc1, doc2])
    db_session.commit()
    
    chunk1 = DocumentChunk(
        document_id=doc1.id,
        chunk_index=0,
        content="Important information about the project",
        token_count=6,
    )
    chunk2 = DocumentChunk(
        document_id=doc2.id,
        chunk_index=0,
        content="Important information about the project",
        token_count=6,
    )
    db_session.add_all([chunk1, chunk2])
    db_session.commit()
    
    # Search in workspace 1
    results = search_by_keywords(db_session, "important", workspace_id=1, top_k=10)
    
    # Should only return results from workspace 1
    assert len(results) == 1
    assert results[0]["workspace_id"] == 1


def test_search_by_keywords_top_k_limit(db_session: Session) -> None:
    """Test that top_k limits results."""
    doc = Document(workspace_id=1, connector_id=1, source_type="github", source_id="repo", title="Repo")
    db_session.add(doc)
    db_session.commit()
    
    # Create multiple chunks
    for i in range(10):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=f"This is chunk {i} with common keyword test",
            token_count=8,
        )
        db_session.add(chunk)
    db_session.commit()
    
    # Search with top_k=3
    results = search_by_keywords(db_session, "keyword", workspace_id=1, top_k=3)
    
    assert len(results) <= 3


def test_search_by_keywords_empty_query(db_session: Session) -> None:
    """Test search with empty query."""
    results = search_by_keywords(db_session, "", workspace_id=1, top_k=10)
    
    assert results == []


def test_search_by_keywords_no_results(db_session: Session) -> None:
    """Test search that returns no results."""
    doc = Document(workspace_id=1, connector_id=1, source_type="jira", source_id="1", title="Issue")
    db_session.add(doc)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="This is about project management",
        token_count=5,
    )
    db_session.add(chunk)
    db_session.commit()
    
    # Search for unrelated term
    results = search_by_keywords(db_session, "nonexistent", workspace_id=1, top_k=10)
    
    assert len(results) == 0


def test_search_by_keywords_returns_metadata(db_session: Session) -> None:
    """Test that search returns all required metadata."""
    doc = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-123",
        title="Test Document",
        url="https://example.com/doc",
    )
    db_session.add(doc)
    db_session.commit()
    
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Test content for search results",
        token_count=5,
        acl_json={"readers": ["user@example.com"]},
    )
    db_session.add(chunk)
    db_session.commit()
    
    results = search_by_keywords(db_session, "search", workspace_id=1, top_k=10)
    
    assert len(results) > 0
    result = results[0]
    assert "chunk_id" in result
    assert "document_id" in result
    assert "content" in result
    assert "title" in result
    assert "url" in result
    assert "source_type" in result
    assert "acl" in result
    assert "score" in result
