"""Tests for hybrid search with Reciprocal Rank Fusion."""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from src.retrieval.hybrid_search import hybrid_search, reciprocal_rank_fusion


def test_reciprocal_rank_fusion_basic() -> None:
    """Test basic RRF merging of two result lists."""
    keyword_results = [
        {"chunk_id": 1, "score": 0.9, "content": "Result 1"},
        {"chunk_id": 2, "score": 0.7, "content": "Result 2"},
        {"chunk_id": 3, "score": 0.5, "content": "Result 3"},
    ]
    
    vector_results = [
        {"chunk_id": 2, "score": 0.95, "content": "Result 2"},  # Appears in both
        {"chunk_id": 4, "score": 0.8, "content": "Result 4"},
        {"chunk_id": 1, "score": 0.6, "content": "Result 1"},  # Appears in both
    ]
    
    merged = reciprocal_rank_fusion(keyword_results, vector_results, k=60)
    
    # Results that appear in both lists should have higher RRF scores
    assert len(merged) > 0
    chunk_ids = [r["chunk_id"] for r in merged]
    
    # Chunks 1 and 2 appear in both lists, so should rank high
    assert 1 in chunk_ids
    assert 2 in chunk_ids


def test_reciprocal_rank_fusion_with_k_parameter() -> None:
    """Test RRF with different k values."""
    list1 = [{"chunk_id": 1, "score": 1.0, "content": "A"}]
    list2 = [{"chunk_id": 1, "score": 1.0, "content": "A"}]
    
    # k=60 is standard
    result_k60 = reciprocal_rank_fusion(list1, list2, k=60)
    
    # k=10 gives higher weight to top ranks
    result_k10 = reciprocal_rank_fusion(list1, list2, k=10)
    
    # Both should include chunk 1
    assert result_k60[0]["chunk_id"] == 1
    assert result_k10[0]["chunk_id"] == 1
    
    # Scores will differ based on k
    assert result_k60[0]["score"] != result_k10[0]["score"]


def test_reciprocal_rank_fusion_empty_lists() -> None:
    """Test RRF with empty input lists."""
    result = reciprocal_rank_fusion([], [], k=60)
    assert result == []


def test_reciprocal_rank_fusion_one_empty_list() -> None:
    """Test RRF with one empty list."""
    list1 = [{"chunk_id": 1, "score": 0.8, "content": "Result"}]
    
    result = reciprocal_rank_fusion(list1, [], k=60)
    
    assert len(result) == 1
    assert result[0]["chunk_id"] == 1


@patch("src.retrieval.hybrid_search.search_by_keywords")
@patch("src.retrieval.hybrid_search.search_by_vector")
def test_hybrid_search_combines_results(
    mock_vector_search,
    mock_keyword_search,
    db_session: Session,
) -> None:
    """Test that hybrid search combines keyword and vector results."""
    # Mock keyword search results
    mock_keyword_search.return_value = [
        {"chunk_id": 1, "score": 0.9, "content": "Keyword match", "title": "Doc 1", "url": None},
        {"chunk_id": 2, "score": 0.7, "content": "Another match", "title": "Doc 2", "url": None},
    ]
    
    # Mock vector search results
    mock_vector_search.return_value = [
        {"chunk_id": 2, "score": 0.95, "content": "Another match", "title": "Doc 2", "url": None},
        {"chunk_id": 3, "score": 0.8, "content": "Vector match", "title": "Doc 3", "url": None},
    ]
    
    results = hybrid_search(
        db_session=db_session,
        query="test query",
        workspace_id=1,
        top_k=10,
    )
    
    # Should call both search methods
    mock_keyword_search.assert_called_once()
    mock_vector_search.assert_called_once()
    
    # Should combine results
    assert len(results) > 0
    chunk_ids = [r["chunk_id"] for r in results]
    
    # All unique chunks should be present
    assert 1 in chunk_ids
    assert 2 in chunk_ids
    assert 3 in chunk_ids


@patch("src.retrieval.hybrid_search.search_by_keywords")
@patch("src.retrieval.hybrid_search.search_by_vector")
def test_hybrid_search_respects_top_k(
    mock_vector_search,
    mock_keyword_search,
    db_session: Session,
) -> None:
    """Test that hybrid search respects top_k limit."""
    # Return many results from each search
    keyword_results = [
        {"chunk_id": i, "score": 0.9 - i*0.05, "content": f"Chunk {i}", "title": f"Doc {i}", "url": None}
        for i in range(20)
    ]
    vector_results = [
        {"chunk_id": i+10, "score": 0.95 - i*0.05, "content": f"Chunk {i+10}", "title": f"Doc {i+10}", "url": None}
        for i in range(20)
    ]
    
    mock_keyword_search.return_value = keyword_results
    mock_vector_search.return_value = vector_results
    
    results = hybrid_search(db_session, "query", workspace_id=1, top_k=5)
    
    # Should limit to top_k
    assert len(results) <= 5


@patch("src.retrieval.hybrid_search.search_by_keywords")
@patch("src.retrieval.hybrid_search.search_by_vector")
def test_hybrid_search_empty_query(
    mock_vector_search,
    mock_keyword_search,
    db_session: Session,
) -> None:
    """Test hybrid search with empty query."""
    results = hybrid_search(db_session, "", workspace_id=1, top_k=10)
    
    assert results == []
    # Should not call search methods
    mock_keyword_search.assert_not_called()
    mock_vector_search.assert_not_called()


def test_reciprocal_rank_fusion_preserves_metadata() -> None:
    """Test that RRF preserves all metadata from results."""
    list1 = [
        {
            "chunk_id": 1,
            "score": 0.9,
            "content": "Content",
            "title": "Title",
            "url": "https://example.com",
            "acl": {"readers": ["user@example.com"]},
        }
    ]
    list2 = []
    
    merged = reciprocal_rank_fusion(list1, list2, k=60)
    
    assert len(merged) == 1
    assert merged[0]["content"] == "Content"
    assert merged[0]["title"] == "Title"
    assert merged[0]["url"] == "https://example.com"
    assert merged[0]["acl"]["readers"] == ["user@example.com"]
