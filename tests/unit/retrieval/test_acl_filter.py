"""Tests for ACL-based permission filtering (fail-closed)."""

import pytest
from typing import Dict, Any, List

from src.retrieval.acl_filter import filter_by_permissions


def test_filter_by_permissions_allows_matching_email() -> None:
    """Test that chunks with matching email in ACL are allowed."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": {"readers": ["user@example.com"]},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == 1


def test_filter_by_permissions_blocks_non_matching_email() -> None:
    """Test that chunks without matching email are blocked."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": {"readers": ["other@example.com"]},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 0


def test_filter_by_permissions_blocks_empty_acl() -> None:
    """Test fail-closed: chunks with empty ACL are blocked."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": {},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 0


def test_filter_by_permissions_blocks_null_acl() -> None:
    """Test fail-closed: chunks with null ACL are blocked."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": None,
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 0


def test_filter_by_permissions_blocks_missing_acl() -> None:
    """Test fail-closed: chunks without ACL field are blocked."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            # ACL field missing
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 0


def test_filter_by_permissions_supports_external_id() -> None:
    """Test matching by external_id (e.g., Slack user ID)."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": {"readers": ["U12345"]},  # Slack user ID
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == 1


def test_filter_by_permissions_supports_channel_membership() -> None:
    """Test channel-based permissions (e.g., Slack channel)."""
    user_identities = [
        {
            "connector_type": "slack",
            "email": "user@example.com",
            "external_id": "U12345",
            "channels": ["C123", "C456"],
        },
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content from channel C123",
            "acl": {"channel": "C123"},
        },
        {
            "chunk_id": 2,
            "content": "Content from channel C789",
            "acl": {"channel": "C789"},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    # Should only include chunk from C123
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == 1


def test_filter_by_permissions_with_multiple_identities() -> None:
    """Test user with multiple connector identities."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
        {"connector_type": "jira", "email": "user@example.com", "external_id": "accountId123"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Slack content",
            "acl": {"readers": ["U12345"]},
        },
        {
            "chunk_id": 2,
            "content": "Jira content",
            "acl": {"readers": ["accountId123"]},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    # Should include both chunks
    assert len(filtered) == 2


def test_filter_by_permissions_allows_public_content() -> None:
    """Test that content marked as public is accessible to all."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "content": "Public content",
            "acl": {"public": True},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == 1


def test_filter_by_permissions_empty_user_identities() -> None:
    """Test that empty user identities blocks all results (fail-closed)."""
    user_identities: List[Dict[str, Any]] = []
    
    results = [
        {
            "chunk_id": 1,
            "content": "Content",
            "acl": {"readers": ["user@example.com"]},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    # Fail-closed: no identities means no access
    assert len(filtered) == 0


def test_filter_by_permissions_preserves_result_structure() -> None:
    """Test that filtering preserves all result fields."""
    user_identities = [
        {"connector_type": "slack", "email": "user@example.com", "external_id": "U12345"},
    ]
    
    results = [
        {
            "chunk_id": 1,
            "document_id": 100,
            "content": "Content",
            "title": "Document Title",
            "url": "https://example.com",
            "score": 0.95,
            "acl": {"readers": ["user@example.com"]},
        },
    ]
    
    filtered = filter_by_permissions(results, user_identities)
    
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == 1
    assert filtered[0]["document_id"] == 100
    assert filtered[0]["title"] == "Document Title"
    assert filtered[0]["score"] == 0.95
