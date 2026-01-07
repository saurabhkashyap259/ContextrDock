"""US3 Scenario 3: Undefined ACL Fail-Closed

Tests that documents with undefined, None, or malformed ACL metadata are
properly excluded from search results (fail-closed security).
"""

import pytest
from datetime import datetime

from src.models.user import User
from src.models.chunk import Chunk
from src.retrieval.hybrid_search import hybrid_search
from src.services.acl_validator import ACLValidator


@pytest.fixture
def test_user(db_session):
    """Create a test user with multiple connector identities."""
    user = User(
        email="test@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {
                "user_id": "U_TEST",
                "team_id": "T_WORKSPACE",
                "display_name": "Test User"
            },
            "jira": {
                "account_id": "JIRA_TEST",
                "email": "test@example.com"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def chunks_with_undefined_acl(db_session):
    """Create chunks with various undefined/malformed ACL states."""
    chunks = []
    
    # Chunk with acl_json = None
    chunk1 = Chunk(
        chunk_id="undefined-001",
        connector_type="slack",
        content="Document with None ACL should be excluded",
        embedding=[0.1] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "random",
            "channel_id": "C_RANDOM",
            "author": "User1"
        },
        acl_json=None,  # Undefined ACL
        created_at=datetime.utcnow()
    )
    
    # Chunk with acl_json = {} (empty dict)
    chunk2 = Chunk(
        chunk_id="undefined-002",
        connector_type="jira",
        content="Document with empty ACL dict should be excluded",
        embedding=[0.15] * 768,
        workspace_id=1,
        metadata={
            "project_key": "TEST",
            "issue_key": "TEST-123"
        },
        acl_json={},  # Empty ACL
        created_at=datetime.utcnow()
    )
    
    # Chunk with missing connector_type in ACL
    chunk3 = Chunk(
        chunk_id="malformed-001",
        connector_type="github",
        content="Document with missing connector_type in ACL",
        embedding=[0.12] * 768,
        workspace_id=1,
        metadata={
            "repo_name": "test-repo",
            "file_path": "README.md"
        },
        acl_json={
            "access_level": "restricted"
            # Missing connector_type field
        },
        created_at=datetime.utcnow()
    )
    
    # Chunk with unknown connector_type
    chunk4 = Chunk(
        chunk_id="malformed-002",
        connector_type="slack",
        content="Document with unknown connector type in ACL",
        embedding=[0.13] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "test",
            "channel_id": "C_TEST"
        },
        acl_json={
            "connector_type": "unknown_connector",
            "access_level": "restricted"
        },
        created_at=datetime.utcnow()
    )
    
    # Valid public chunk for comparison
    chunk5 = Chunk(
        chunk_id="valid-001",
        connector_type="slack",
        content="Valid public document should be included",
        embedding=[0.11] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "general",
            "channel_id": "C_GENERAL"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "public"
        },
        created_at=datetime.utcnow()
    )
    
    chunks.extend([chunk1, chunk2, chunk3, chunk4, chunk5])
    
    for chunk in chunks:
        db_session.add(chunk)
    
    db_session.commit()
    
    return chunks


def test_none_acl_excluded(test_user, chunks_with_undefined_acl, db_session):
    """Documents with None ACL should be excluded (fail-closed)."""
    query = "document with None ACL"
    
    user_dict = {
        "id": test_user.id,
        "email": test_user.email,
        "workspace_id": test_user.workspace_id,
        "connector_identities": test_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should only see the valid public chunk, not the None ACL chunk
    chunk_ids = [r["chunk_id"] for r in results]
    assert "undefined-001" not in chunk_ids, "Chunk with None ACL should be excluded"
    
    # Verify we can see the valid chunk
    assert "valid-001" in chunk_ids, "Valid public chunk should be included"


def test_empty_acl_excluded(test_user, chunks_with_undefined_acl, db_session):
    """Documents with empty ACL dict should be excluded (fail-closed)."""
    query = "document with empty ACL"
    
    user_dict = {
        "id": test_user.id,
        "email": test_user.email,
        "workspace_id": test_user.workspace_id,
        "connector_identities": test_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should not see the empty ACL chunk
    chunk_ids = [r["chunk_id"] for r in results]
    assert "undefined-002" not in chunk_ids, "Chunk with empty ACL should be excluded"


def test_malformed_acl_excluded(test_user, chunks_with_undefined_acl, db_session):
    """Documents with malformed ACL should be excluded (fail-closed)."""
    query = "document"
    
    user_dict = {
        "id": test_user.id,
        "email": test_user.email,
        "workspace_id": test_user.workspace_id,
        "connector_identities": test_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should not see chunks with malformed ACL
    chunk_ids = [r["chunk_id"] for r in results]
    assert "malformed-001" not in chunk_ids, "Chunk with missing connector_type should be excluded"
    assert "malformed-002" not in chunk_ids, "Chunk with unknown connector_type should be excluded"
    
    # Should only see the valid public chunk
    assert len(results) == 1, f"Expected 1 result (valid chunk only), got {len(results)}"
    assert "valid-001" in chunk_ids


def test_acl_validator_fail_closed_none():
    """ACL validator should deny access for None ACL."""
    validator = ACLValidator()
    
    user = {
        "id": 1,
        "connector_identities": {
            "slack": {"user_id": "U_TEST"}
        }
    }
    
    result = validator.check_access(user, None)
    
    assert result.allowed is False
    assert "undefined" in result.reason.lower() or "none" in result.reason.lower()


def test_acl_validator_fail_closed_empty():
    """ACL validator should deny access for empty ACL dict."""
    validator = ACLValidator()
    
    user = {
        "id": 1,
        "connector_identities": {
            "slack": {"user_id": "U_TEST"}
        }
    }
    
    result = validator.check_access(user, {})
    
    assert result.allowed is False
    assert "empty" in result.reason.lower() or "undefined" in result.reason.lower()


def test_acl_validator_fail_closed_missing_connector_type():
    """ACL validator should deny access when connector_type is missing."""
    validator = ACLValidator()
    
    user = {
        "id": 1,
        "connector_identities": {
            "slack": {"user_id": "U_TEST"}
        }
    }
    
    acl = {
        "access_level": "restricted"
        # Missing connector_type
    }
    
    result = validator.check_access(user, acl)
    
    assert result.allowed is False


def test_acl_validator_unknown_connector_type():
    """ACL validator should deny access for unknown connector types."""
    validator = ACLValidator()
    
    user = {
        "id": 1,
        "connector_identities": {
            "slack": {"user_id": "U_TEST"}
        }
    }
    
    acl = {
        "connector_type": "unknown_system",
        "access_level": "restricted"
    }
    
    result = validator.check_access(user, acl)
    
    assert result.allowed is False
    assert "unsupported" in result.reason.lower() or "unknown" in result.reason.lower()


def test_mixed_valid_and_invalid_acls(test_user, db_session):
    """Test that only documents with valid ACLs are returned."""
    # Create a mix of valid and invalid ACL documents
    chunks = [
        # Valid public
        Chunk(
            chunk_id="mix-valid-1",
            connector_type="slack",
            content="Valid public document about testing",
            embedding=[0.1] * 768,
            workspace_id=1,
            metadata={"channel_name": "general", "channel_id": "C_GEN"},
            acl_json={
                "connector_type": "slack",
                "access_level": "public"
            },
            created_at=datetime.utcnow()
        ),
        # Valid restricted (user has access)
        Chunk(
            chunk_id="mix-valid-2",
            connector_type="slack",
            content="Valid restricted document about testing",
            embedding=[0.11] * 768,
            workspace_id=1,
            metadata={"channel_name": "private", "channel_id": "C_PRIV"},
            acl_json={
                "connector_type": "slack",
                "access_level": "restricted",
                "allowed_user_ids": ["U_TEST"]
            },
            created_at=datetime.utcnow()
        ),
        # Invalid - None ACL
        Chunk(
            chunk_id="mix-invalid-1",
            connector_type="slack",
            content="Invalid document with None ACL about testing",
            embedding=[0.12] * 768,
            workspace_id=1,
            metadata={"channel_name": "broken", "channel_id": "C_BROKEN"},
            acl_json=None,
            created_at=datetime.utcnow()
        ),
        # Invalid - empty ACL
        Chunk(
            chunk_id="mix-invalid-2",
            connector_type="jira",
            content="Invalid document with empty ACL about testing",
            embedding=[0.13] * 768,
            workspace_id=1,
            metadata={"project_key": "BROKEN"},
            acl_json={},
            created_at=datetime.utcnow()
        )
    ]
    
    for chunk in chunks:
        db_session.add(chunk)
    db_session.commit()
    
    query = "testing"
    
    user_dict = {
        "id": test_user.id,
        "email": test_user.email,
        "workspace_id": test_user.workspace_id,
        "connector_identities": test_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should only see the 2 valid documents
    assert len(results) == 2, f"Expected 2 results (valid only), got {len(results)}"
    
    chunk_ids = [r["chunk_id"] for r in results]
    assert "mix-valid-1" in chunk_ids
    assert "mix-valid-2" in chunk_ids
    assert "mix-invalid-1" not in chunk_ids
    assert "mix-invalid-2" not in chunk_ids


def test_batch_acl_check_with_undefined(test_user):
    """Test batch ACL checking handles undefined ACLs correctly."""
    validator = ACLValidator()
    
    user_dict = {
        "id": test_user.id,
        "connector_identities": test_user.connector_identities
    }
    
    acl_list = [
        {
            "connector_type": "slack",
            "access_level": "public"
        },
        None,  # Undefined
        {},    # Empty
        {
            "connector_type": "slack",
            "access_level": "restricted",
            "allowed_user_ids": ["U_TEST"]
        },
        {
            "connector_type": "unknown_connector",
            "access_level": "public"
        }
    ]
    
    results = validator.batch_check_access(user_dict, acl_list)
    
    # Results should match the ACL list length
    assert len(results) == 5
    
    # First ACL: public - allowed
    assert results[0].allowed is True
    
    # Second ACL: None - denied (fail-closed)
    assert results[1].allowed is False
    
    # Third ACL: empty - denied (fail-closed)
    assert results[2].allowed is False
    
    # Fourth ACL: valid restricted with access - allowed
    assert results[3].allowed is True
    
    # Fifth ACL: unknown connector - denied
    assert results[4].allowed is False


def test_fail_closed_protects_sensitive_data(test_user, db_session):
    """Fail-closed ensures sensitive data with broken ACL is not exposed."""
    # Simulate a chunk that should be restricted but has broken ACL
    sensitive_chunk = Chunk(
        chunk_id="sensitive-001",
        connector_type="github",
        content="API keys and passwords for production systems",
        embedding=[0.1] * 768,
        workspace_id=1,
        metadata={
            "repo_name": "secrets",
            "file_path": ".env"
        },
        acl_json=None,  # Broken ACL - should fail closed
        created_at=datetime.utcnow()
    )
    
    db_session.add(sensitive_chunk)
    db_session.commit()
    
    query = "API keys passwords"
    
    user_dict = {
        "id": test_user.id,
        "email": test_user.email,
        "workspace_id": test_user.workspace_id,
        "connector_identities": test_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Sensitive data should NOT be exposed
    chunk_ids = [r["chunk_id"] for r in results]
    assert "sensitive-001" not in chunk_ids, \
        "Sensitive data with broken ACL should not be exposed (fail-closed)"
    
    # Verify no results at all (only the sensitive chunk matches)
    assert len(results) == 0, \
        "No results should be returned when only matches have broken ACLs"
