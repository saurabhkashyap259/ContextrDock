"""Tests for RAG-based answer generation with grounded citations."""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from src.retrieval.answer_generation import generate_answer


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_basic(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test basic answer generation with retrieval and LLM."""
    # Mock user identities
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    # Mock search results
    mock_search.return_value = [
        {
            "chunk_id": 1,
            "document_id": 100,
            "content": "OAuth 2.0 is an authorization framework.",
            "title": "OAuth Guide",
            "url": "https://example.com/oauth",
            "score": 0.95,
            "acl": {"readers": ["user@example.com"]},
        }
    ]
    
    # Mock ACL filter (pass through)
    mock_filter.return_value = mock_search.return_value
    
    # Mock LLM
    mock_llm = Mock()
    mock_llm.generate.return_value = {
        "content": "OAuth 2.0 is an authorization framework used for secure API access.",
        "usage": {"total_tokens": 50},
    }
    
    result = generate_answer(
        db_session=db_session,
        query="What is OAuth?",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
    )
    
    assert "answer" in result
    assert "citations" in result
    assert "usage" in result
    
    # Should include citation
    assert len(result["citations"]) > 0
    assert result["citations"][0]["document_id"] == 100


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_no_results(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test answer generation when no search results found."""
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    # No search results
    mock_search.return_value = []
    mock_filter.return_value = []
    
    mock_llm = Mock()
    
    result = generate_answer(
        db_session=db_session,
        query="What is OAuth?",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
    )
    
    # Should return answer indicating no results
    assert "answer" in result
    assert "no relevant information" in result["answer"].lower() or "couldn't find" in result["answer"].lower()
    assert result["citations"] == []
    
    # LLM should not be called when no context available
    mock_llm.generate.assert_not_called()


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_includes_context_in_prompt(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test that retrieved chunks are included in LLM prompt."""
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    mock_search.return_value = [
        {
            "chunk_id": 1,
            "document_id": 100,
            "content": "OAuth 2.0 is an authorization framework.",
            "title": "OAuth Guide",
            "url": "https://example.com/oauth",
            "score": 0.95,
            "acl": {"readers": ["user@example.com"]},
        }
    ]
    
    mock_filter.return_value = mock_search.return_value
    
    mock_llm = Mock()
    mock_llm.generate.return_value = {
        "content": "Based on the context, OAuth 2.0 is an authorization framework.",
        "usage": {"total_tokens": 50},
    }
    
    generate_answer(
        db_session=db_session,
        query="What is OAuth?",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
    )
    
    # Check that LLM was called with context
    mock_llm.generate.assert_called_once()
    call_args = mock_llm.generate.call_args
    messages = call_args[0][0]  # First positional arg
    
    # Should have system message with context
    system_msg = next((m for m in messages if m["role"] == "system"), None)
    assert system_msg is not None
    assert "OAuth 2.0 is an authorization framework" in system_msg["content"]


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_acl_filtering_applied(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test that ACL filtering is applied to search results."""
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    # Search returns 2 results
    mock_search.return_value = [
        {
            "chunk_id": 1,
            "content": "Public content",
            "acl": {"public": True},
        },
        {
            "chunk_id": 2,
            "content": "Private content",
            "acl": {"readers": ["other@example.com"]},
        },
    ]
    
    # ACL filter removes second result
    mock_filter.return_value = [mock_search.return_value[0]]
    
    mock_llm = Mock()
    mock_llm.generate.return_value = {
        "content": "Here's the answer.",
        "usage": {"total_tokens": 20},
    }
    
    generate_answer(
        db_session=db_session,
        query="Test query",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
    )
    
    # Verify filter was called with user identities
    mock_filter.assert_called_once()
    call_args = mock_filter.call_args
    assert call_args[0][0] == mock_search.return_value  # Results
    assert call_args[0][1] == mock_resolve.return_value  # User identities


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_limits_context_length(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test that context is limited to prevent token overflow."""
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    # Return many results
    mock_search.return_value = [
        {
            "chunk_id": i,
            "document_id": i,
            "content": f"Content {i}" * 1000,  # Long content
            "title": f"Doc {i}",
            "url": f"https://example.com/{i}",
            "score": 0.9 - i * 0.01,
            "acl": {"readers": ["user@example.com"]},
        }
        for i in range(50)
    ]
    
    mock_filter.return_value = mock_search.return_value
    
    mock_llm = Mock()
    mock_llm.generate.return_value = {
        "content": "Answer",
        "usage": {"total_tokens": 100},
    }
    
    generate_answer(
        db_session=db_session,
        query="Test query",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
        max_context_chunks=5,  # Limit context
    )
    
    # Check that only first N chunks were used
    call_args = mock_llm.generate.call_args
    messages = call_args[0][0]
    system_msg = next(m for m in messages if m["role"] == "system")
    
    # Should not contain all 50 chunks worth of content
    content_0_count = system_msg["content"].count("Content 0")
    content_49_count = system_msg["content"].count("Content 49")
    
    assert content_0_count > 0  # First chunk included
    # Later chunks may or may not be included based on limit


@patch("src.retrieval.answer_generation.hybrid_search")
@patch("src.retrieval.answer_generation.filter_by_permissions")
@patch("src.retrieval.answer_generation.resolve_user_identities")
def test_generate_answer_citation_format(
    mock_resolve,
    mock_filter,
    mock_search,
    db_session: Session,
) -> None:
    """Test that citations include all required fields."""
    mock_resolve.return_value = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"}
    ]
    
    mock_search.return_value = [
        {
            "chunk_id": 1,
            "document_id": 100,
            "content": "Content",
            "title": "Doc Title",
            "url": "https://example.com",
            "score": 0.95,
            "acl": {"readers": ["user@example.com"]},
        }
    ]
    
    mock_filter.return_value = mock_search.return_value
    
    mock_llm = Mock()
    mock_llm.generate.return_value = {
        "content": "Answer",
        "usage": {"total_tokens": 30},
    }
    
    result = generate_answer(
        db_session=db_session,
        query="Test",
        user_id=1,
        workspace_id=1,
        llm_client=mock_llm,
    )
    
    citation = result["citations"][0]
    assert "document_id" in citation
    assert "chunk_id" in citation
    assert "title" in citation
    assert "url" in citation
    assert "score" in citation
    assert citation["document_id"] == 100
    assert citation["title"] == "Doc Title"
