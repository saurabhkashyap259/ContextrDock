"""US3 Scenario 4: Permission Changes After Sync

Tests that permission changes take effect immediately after user identity
mappings are updated via the admin API. Validates dynamic permission management.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from src.database import get_db
from src.models.user import User
from src.models.chunk import Chunk
from src.retrieval.hybrid_search import hybrid_search
from src.api.routes.admin import router as admin_router
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app with admin router."""
    app = FastAPI()
    app.include_router(admin_router)
    
    # Override DB dependency
    def override_get_db():
        from src.database import SessionLocal
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def dynamic_user(db_session):
    """Create user whose permissions will change during test."""
    user = User(
        email="dynamic@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={}  # Start with no identities
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def private_slack_channel(db_session):
    """Create chunks from a private Slack channel."""
    chunks = []
    
    for i in range(3):
        chunk = Chunk(
            chunk_id=f"slack-private-{i+1:03d}",
            connector_type="slack",
            content=f"Private channel message {i+1}: Important team discussion",
            embedding=[0.1 + i*0.01] * 768,
            workspace_id=1,
            metadata={
                "channel_name": "engineering-private",
                "channel_id": "C_ENG_PRIVATE",
                "author": "Team Lead",
                "timestamp": f"2024-01-15T10:{30+i}:00Z"
            },
            acl_json={
                "connector_type": "slack",
                "access_level": "restricted",
                "channel_type": "private",
                "allowed_user_ids": ["U_TEAM_LEAD", "U_ENGINEER1", "U_ENGINEER2"]
            },
            created_at=datetime.utcnow()
        )
        chunks.append(chunk)
        db_session.add(chunk)
    
    db_session.commit()
    return chunks


def test_no_access_before_identity_added(dynamic_user, private_slack_channel, db_session):
    """User without connector identity should not see private channel results."""
    query = "team discussion"
    
    user_dict = {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should see no results (user has no Slack identity)
    assert len(results) == 0, f"Expected 0 results, got {len(results)}"


def test_access_granted_after_identity_added(dynamic_user, private_slack_channel, db_session, client):
    """User gains access after admin adds their connector identity."""
    query = "team discussion"
    
    # Step 1: Verify no access initially
    user_dict = {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    results_before = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    assert len(results_before) == 0, "Should have no access initially"
    
    # Step 2: Admin adds Slack identity with access to channel
    update_response = client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {
                    "user_id": "U_ENGINEER1",  # User is now engineer1 (in allowed list)
                    "team_id": "T_WORKSPACE",
                    "display_name": "Dynamic User"
                }
            }
        }
    )
    
    assert update_response.status_code == 200, f"Identity update failed: {update_response.text}"
    
    # Step 3: Refresh user from DB to get updated identities
    db_session.refresh(dynamic_user)
    
    user_dict_after = {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    # Step 4: Query again - should now see results
    results_after = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict_after,
        top_k=10
    )
    
    assert len(results_after) == 3, f"Expected 3 results after identity added, got {len(results_after)}"
    
    # Verify all results are from the private channel
    for result in results_after:
        assert result["metadata"]["channel_id"] == "C_ENG_PRIVATE"


def test_access_revoked_after_identity_removed(dynamic_user, private_slack_channel, db_session, client):
    """User loses access after admin removes their identity from allowed list."""
    query = "team discussion"
    
    # Step 1: Give user access first
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {
                    "user_id": "U_ENGINEER1",
                    "team_id": "T_WORKSPACE",
                    "display_name": "Dynamic User"
                }
            }
        }
    )
    
    db_session.refresh(dynamic_user)
    
    user_dict = {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    # Verify access granted
    results_with_access = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    assert len(results_with_access) == 3, "Should have access after identity added"
    
    # Step 2: Change user's Slack ID to one NOT in allowed list
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {
                    "user_id": "U_DIFFERENT_USER",  # Not in allowed_user_ids
                    "team_id": "T_WORKSPACE",
                    "display_name": "Dynamic User"
                }
            }
        }
    )
    
    db_session.refresh(dynamic_user)
    
    user_dict_after = {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    # Step 3: Query again - should now be denied
    results_without_access = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict_after,
        top_k=10
    )
    
    assert len(results_without_access) == 0, \
        f"Expected 0 results after access revoked, got {len(results_without_access)}"


def test_partial_identity_update_preserves_other_connectors(dynamic_user, db_session, client):
    """Updating one connector identity should preserve other connector identities."""
    # Step 1: Add Slack and Jira identities
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {
                    "user_id": "U_ENGINEER1",
                    "team_id": "T_WORKSPACE"
                },
                "jira": {
                    "account_id": "JIRA_USER123",
                    "email": "dynamic@example.com"
                }
            }
        }
    )
    
    db_session.refresh(dynamic_user)
    
    # Verify both identities present
    assert "slack" in dynamic_user.connector_identities
    assert "jira" in dynamic_user.connector_identities
    
    # Step 2: Update only GitHub identity (should preserve Slack and Jira)
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "github": {
                    "login": "dynamicuser",
                    "user_id": 98765
                }
            }
        }
    )
    
    db_session.refresh(dynamic_user)
    
    # Verify all three identities present
    assert "slack" in dynamic_user.connector_identities
    assert "jira" in dynamic_user.connector_identities
    assert "github" in dynamic_user.connector_identities
    
    # Verify Slack identity unchanged
    assert dynamic_user.connector_identities["slack"]["user_id"] == "U_ENGINEER1"
    assert dynamic_user.connector_identities["jira"]["account_id"] == "JIRA_USER123"
    assert dynamic_user.connector_identities["github"]["login"] == "dynamicuser"


def test_multiple_permission_changes_in_sequence(dynamic_user, private_slack_channel, db_session, client):
    """Test multiple permission changes happen in correct sequence."""
    query = "team discussion"
    
    # Iteration 1: No access
    user_dict = lambda: {
        "id": dynamic_user.id,
        "email": dynamic_user.email,
        "workspace_id": dynamic_user.workspace_id,
        "connector_identities": dynamic_user.connector_identities
    }
    
    results_1 = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_1) == 0, "Iteration 1: No access"
    
    # Iteration 2: Grant access
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {"user_id": "U_ENGINEER1", "team_id": "T_WORKSPACE"}
            }
        }
    )
    db_session.refresh(dynamic_user)
    
    results_2 = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_2) == 3, "Iteration 2: Access granted"
    
    # Iteration 3: Revoke access
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {"user_id": "U_DIFFERENT", "team_id": "T_WORKSPACE"}
            }
        }
    )
    db_session.refresh(dynamic_user)
    
    results_3 = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_3) == 0, "Iteration 3: Access revoked"
    
    # Iteration 4: Grant access again
    client.patch(
        f"/v1/admin/users/{dynamic_user.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {"user_id": "U_ENGINEER2", "team_id": "T_WORKSPACE"}
            }
        }
    )
    db_session.refresh(dynamic_user)
    
    results_4 = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_4) == 3, "Iteration 4: Access granted again"


def test_real_time_permission_changes_with_github(db_session, client):
    """Test permission changes for GitHub private repository."""
    # Create user without GitHub access
    user = User(
        email="githubuser@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={}
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create private GitHub repo chunk
    github_chunk = Chunk(
        chunk_id="github-private-001",
        connector_type="github",
        content="Private repository implementation details",
        embedding=[0.1] * 768,
        workspace_id=1,
        metadata={
            "repo_name": "private-repo",
            "repo_full_name": "myorg/private-repo",
            "file_path": "src/main.py"
        },
        acl_json={
            "connector_type": "github",
            "access_level": "restricted",
            "repo_visibility": "private",
            "collaborators": ["devuser", "maintainer"]
        },
        created_at=datetime.utcnow()
    )
    db_session.add(github_chunk)
    db_session.commit()
    
    query = "implementation details"
    
    user_dict = lambda: {
        "id": user.id,
        "email": user.email,
        "workspace_id": user.workspace_id,
        "connector_identities": user.connector_identities
    }
    
    # No access initially
    results_before = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_before) == 0, "Should have no GitHub access initially"
    
    # Add GitHub identity (as collaborator)
    client.patch(
        f"/v1/admin/users/{user.id}/identity-mappings",
        json={
            "connector_identities": {
                "github": {
                    "login": "devuser",  # Listed in collaborators
                    "user_id": 12345
                }
            }
        }
    )
    db_session.refresh(user)
    
    # Should now have access
    results_after = hybrid_search(query=query, workspace_id=1, user=user_dict(), top_k=10)
    assert len(results_after) == 1, "Should have GitHub access after identity added"
    assert results_after[0]["connector_type"] == "github"


def test_permission_change_affects_only_target_user(db_session, client, private_slack_channel):
    """Verify permission changes affect only the target user, not others."""
    # Create two users
    user1 = User(
        email="user1@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {"user_id": "U_ENGINEER1", "team_id": "T_WORKSPACE"}
        }
    )
    
    user2 = User(
        email="user2@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {"user_id": "U_ENGINEER2", "team_id": "T_WORKSPACE"}
        }
    )
    
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    
    query = "team discussion"
    
    # Both users should have access initially
    user1_dict = {
        "id": user1.id,
        "email": user1.email,
        "workspace_id": user1.workspace_id,
        "connector_identities": user1.connector_identities
    }
    
    user2_dict = {
        "id": user2.id,
        "email": user2.email,
        "workspace_id": user2.workspace_id,
        "connector_identities": user2.connector_identities
    }
    
    results_user1_before = hybrid_search(query=query, workspace_id=1, user=user1_dict, top_k=10)
    results_user2_before = hybrid_search(query=query, workspace_id=1, user=user2_dict, top_k=10)
    
    assert len(results_user1_before) == 3, "User1 should have access"
    assert len(results_user2_before) == 3, "User2 should have access"
    
    # Revoke user1's access
    client.patch(
        f"/v1/admin/users/{user1.id}/identity-mappings",
        json={
            "connector_identities": {
                "slack": {"user_id": "U_DIFFERENT", "team_id": "T_WORKSPACE"}
            }
        }
    )
    db_session.refresh(user1)
    
    user1_dict["connector_identities"] = user1.connector_identities
    
    # User1 should lose access, User2 should still have access
    results_user1_after = hybrid_search(query=query, workspace_id=1, user=user1_dict, top_k=10)
    results_user2_after = hybrid_search(query=query, workspace_id=1, user=user2_dict, top_k=10)
    
    assert len(results_user1_after) == 0, "User1 should lose access"
    assert len(results_user2_after) == 3, "User2 should still have access"
