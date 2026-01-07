"""US3 Scenario 1: Restricted Channel Filtering

Tests that private Slack channels are properly filtered based on user permissions.
Only users who are members of a private channel should see its results.
"""

import pytest
from datetime import datetime

from src.database import get_db
from src.models.user import User
from src.models.chunk import Chunk
from src.retrieval.hybrid_search import hybrid_search
from src.services.acl_validator import ACLValidator


@pytest.fixture
def alice(db_session):
    """Create Alice user who is a member of the private channel."""
    user = User(
        email="alice@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {
                "user_id": "U_ALICE",
                "team_id": "T_WORKSPACE",
                "display_name": "Alice"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def bob(db_session):
    """Create Bob user who is NOT a member of the private channel."""
    user = User(
        email="bob@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {
                "user_id": "U_BOB",
                "team_id": "T_WORKSPACE",
                "display_name": "Bob"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def private_channel_chunks(db_session, alice):
    """Create chunks from a private Slack channel.
    
    Channel is private and Alice is a member.
    """
    chunks = []
    
    # Chunk 1: Engineering discussion
    chunk1 = Chunk(
        chunk_id="slack-private-001",
        connector_type="slack",
        content="Discussing new authentication system architecture",
        embedding=[0.1] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "engineering-private",
            "channel_id": "C_PRIVATE",
            "author": "Alice",
            "timestamp": "2024-01-15T10:30:00Z"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_type": "private",
            "allowed_user_ids": ["U_ALICE", "U_CHARLIE"]  # Alice and Charlie are members
        },
        created_at=datetime.utcnow()
    )
    
    # Chunk 2: Technical decision
    chunk2 = Chunk(
        chunk_id="slack-private-002",
        connector_type="slack",
        content="JWT tokens vs session cookies for auth",
        embedding=[0.2] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "engineering-private",
            "channel_id": "C_PRIVATE",
            "author": "Charlie",
            "timestamp": "2024-01-15T10:45:00Z"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_type": "private",
            "allowed_user_ids": ["U_ALICE", "U_CHARLIE"]
        },
        created_at=datetime.utcnow()
    )
    
    # Chunk 3: Security discussion
    chunk3 = Chunk(
        chunk_id="slack-private-003",
        connector_type="slack",
        content="OAuth2 implementation details and security considerations",
        embedding=[0.15] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "engineering-private",
            "channel_id": "C_PRIVATE",
            "author": "Alice",
            "timestamp": "2024-01-15T11:00:00Z"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_type": "private",
            "allowed_user_ids": ["U_ALICE", "U_CHARLIE"]
        },
        created_at=datetime.utcnow()
    )
    
    chunks.extend([chunk1, chunk2, chunk3])
    
    for chunk in chunks:
        db_session.add(chunk)
    
    db_session.commit()
    
    return chunks


def test_member_sees_private_channel_results(alice, private_channel_chunks, db_session):
    """Alice (member) should see results from the private channel."""
    # Query for authentication content
    query = "authentication system OAuth"
    
    # Convert alice to dict format expected by hybrid_search
    alice_dict = {
        "id": alice.id,
        "email": alice.email,
        "workspace_id": alice.workspace_id,
        "connector_identities": alice.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=alice_dict,
        top_k=10
    )
    
    # Alice should see all 3 chunks from the private channel
    assert len(results) == 3, f"Expected 3 results, got {len(results)}"
    
    # Verify all results are from the private channel
    for result in results:
        assert result["metadata"]["channel_id"] == "C_PRIVATE"
        assert result["metadata"]["channel_name"] == "engineering-private"
    
    # Verify content is related to query
    result_contents = [r["content"] for r in results]
    assert any("authentication" in content.lower() for content in result_contents)
    assert any("oauth" in content.lower() for content in result_contents)


def test_non_member_sees_no_results(bob, private_channel_chunks, db_session):
    """Bob (non-member) should NOT see any results from the private channel."""
    # Query for the same authentication content
    query = "authentication system OAuth"
    
    # Convert bob to dict format
    bob_dict = {
        "id": bob.id,
        "email": bob.email,
        "workspace_id": bob.workspace_id,
        "connector_identities": bob.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=bob_dict,
        top_k=10
    )
    
    # Bob should see NO results (all filtered out by ACL)
    assert len(results) == 0, f"Expected 0 results for non-member, got {len(results)}"


def test_acl_validator_directly_member(alice):
    """Test ACL validator directly - member should get access."""
    validator = ACLValidator()
    
    acl_metadata = {
        "connector_type": "slack",
        "access_level": "restricted",
        "channel_type": "private",
        "allowed_user_ids": ["U_ALICE", "U_CHARLIE"]
    }
    
    alice_dict = {
        "id": alice.id,
        "connector_identities": alice.connector_identities
    }
    
    result = validator.check_access(alice_dict, acl_metadata)
    
    assert result.allowed is True
    assert "allowed" in result.reason.lower()


def test_acl_validator_directly_non_member(bob):
    """Test ACL validator directly - non-member should be denied."""
    validator = ACLValidator()
    
    acl_metadata = {
        "connector_type": "slack",
        "access_level": "restricted",
        "channel_type": "private",
        "allowed_user_ids": ["U_ALICE", "U_CHARLIE"]
    }
    
    bob_dict = {
        "id": bob.id,
        "connector_identities": bob.connector_identities
    }
    
    result = validator.check_access(bob_dict, acl_metadata)
    
    assert result.allowed is False
    assert "not in allowed" in result.reason.lower() or "denied" in result.reason.lower()


def test_mixed_public_and_private_channels(alice, bob, db_session):
    """Test that public channels are visible to all, while private channels are filtered.
    
    - Alice sees both public and private channels
    - Bob sees only public channels
    """
    # Add a public channel chunk
    public_chunk = Chunk(
        chunk_id="slack-public-001",
        connector_type="slack",
        content="General announcement about authentication updates",
        embedding=[0.12] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "general",
            "channel_id": "C_GENERAL",
            "author": "Admin",
            "timestamp": "2024-01-15T09:00:00Z"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "public",
            "channel_type": "public"
        },
        created_at=datetime.utcnow()
    )
    db_session.add(public_chunk)
    db_session.commit()
    
    query = "authentication"
    
    # Alice should see 4 results (3 private + 1 public)
    alice_dict = {
        "id": alice.id,
        "email": alice.email,
        "workspace_id": alice.workspace_id,
        "connector_identities": alice.connector_identities
    }
    
    alice_results = hybrid_search(
        query=query,
        workspace_id=1,
        user=alice_dict,
        top_k=10
    )
    
    assert len(alice_results) == 4, f"Alice should see 4 results, got {len(alice_results)}"
    
    # Verify Alice sees both channels
    channel_ids = [r["metadata"]["channel_id"] for r in alice_results]
    assert "C_PRIVATE" in channel_ids
    assert "C_GENERAL" in channel_ids
    
    # Bob should see only 1 result (the public one)
    bob_dict = {
        "id": bob.id,
        "email": bob.email,
        "workspace_id": bob.workspace_id,
        "connector_identities": bob.connector_identities
    }
    
    bob_results = hybrid_search(
        query=query,
        workspace_id=1,
        user=bob_dict,
        top_k=10
    )
    
    assert len(bob_results) == 1, f"Bob should see 1 result, got {len(bob_results)}"
    assert bob_results[0]["metadata"]["channel_id"] == "C_GENERAL"
    assert bob_results[0]["metadata"]["channel_name"] == "general"


def test_empty_query_with_acl_filtering(alice, bob, private_channel_chunks, db_session):
    """Test that ACL filtering works even with empty/broad queries."""
    # Empty query should still respect ACL permissions
    query = ""
    
    alice_dict = {
        "id": alice.id,
        "email": alice.email,
        "workspace_id": alice.workspace_id,
        "connector_identities": alice.connector_identities
    }
    
    bob_dict = {
        "id": bob.id,
        "email": bob.email,
        "workspace_id": bob.workspace_id,
        "connector_identities": bob.connector_identities
    }
    
    # Alice should see results
    alice_results = hybrid_search(
        query=query,
        workspace_id=1,
        user=alice_dict,
        top_k=10
    )
    
    assert len(alice_results) > 0, "Alice should see results even with empty query"
    
    # Bob should see no results (all are from private channel)
    bob_results = hybrid_search(
        query=query,
        workspace_id=1,
        user=bob_dict,
        top_k=10
    )
    
    assert len(bob_results) == 0, "Bob should see no results from private channel"
