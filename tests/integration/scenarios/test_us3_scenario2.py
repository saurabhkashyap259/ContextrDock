"""US3 Scenario 2: Multi-Connector Filtering

Tests that documents from multiple connectors are properly filtered based on
user's connector identities. Users should only see results from connectors
they have access to.
"""

import pytest
from datetime import datetime

from src.models.user import User
from src.models.chunk import Chunk
from src.retrieval.hybrid_search import hybrid_search


@pytest.fixture
def slack_only_user(db_session):
    """User with only Slack identity."""
    user = User(
        email="slack_user@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {
                "user_id": "U_SLACK_USER",
                "team_id": "T_WORKSPACE",
                "display_name": "Slack User"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def full_access_user(db_session):
    """User with all connector identities."""
    user = User(
        email="admin@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "slack": {
                "user_id": "U_ADMIN",
                "team_id": "T_WORKSPACE",
                "display_name": "Admin"
            },
            "jira": {
                "account_id": "JIRA_ADMIN",
                "email": "admin@example.com"
            },
            "github": {
                "login": "admin-user",
                "user_id": 98765,
                "organizations": ["myorg"]
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def multi_connector_chunks(db_session):
    """Create chunks from multiple connectors with different access levels."""
    chunks = []
    
    # Slack public channel - everyone can see
    slack_chunk = Chunk(
        chunk_id="slack-001",
        connector_type="slack",
        content="Sprint planning meeting notes for Q1 2024",
        embedding=[0.1] * 768,
        workspace_id=1,
        metadata={
            "channel_name": "planning",
            "channel_id": "C_PLANNING",
            "author": "Manager",
            "timestamp": "2024-01-10T10:00:00Z"
        },
        acl_json={
            "connector_type": "slack",
            "access_level": "public",
            "channel_type": "public"
        },
        created_at=datetime.utcnow()
    )
    
    # Jira restricted project - requires Jira identity
    jira_chunk = Chunk(
        chunk_id="jira-001",
        connector_type="jira",
        content="Sprint tasks: Implement user authentication, setup CI/CD pipeline",
        embedding=[0.15] * 768,
        workspace_id=1,
        metadata={
            "project_key": "ENG",
            "project_name": "Engineering",
            "issue_key": "ENG-123",
            "issue_type": "Epic"
        },
        acl_json={
            "connector_type": "jira",
            "access_level": "restricted",
            "project_visibility": "private",
            "allowed_account_ids": ["JIRA_ADMIN", "JIRA_DEV1", "JIRA_DEV2"]
        },
        created_at=datetime.utcnow()
    )
    
    # GitHub private repo - requires GitHub identity and org membership
    github_chunk = Chunk(
        chunk_id="github-001",
        connector_type="github",
        content="Sprint implementation guide: authentication service architecture",
        embedding=[0.12] * 768,
        workspace_id=1,
        metadata={
            "repo_name": "auth-service",
            "repo_full_name": "myorg/auth-service",
            "file_path": "docs/architecture.md",
            "branch": "main"
        },
        acl_json={
            "connector_type": "github",
            "access_level": "restricted",
            "repo_visibility": "private",
            "org_name": "myorg",
            "collaborators": ["admin-user", "dev-user"],
            "org_members_can_read": True
        },
        created_at=datetime.utcnow()
    )
    
    # Confluence restricted space - requires Confluence identity
    confluence_chunk = Chunk(
        chunk_id="confluence-001",
        connector_type="confluence",
        content="Sprint retrospective: authentication improvements and lessons learned",
        embedding=[0.13] * 768,
        workspace_id=1,
        metadata={
            "space_key": "ENGDOCS",
            "space_name": "Engineering Documentation",
            "page_title": "Q1 2024 Retrospective",
            "page_id": "12345"
        },
        acl_json={
            "connector_type": "confluence",
            "access_level": "restricted",
            "space_visibility": "private",
            "allowed_account_ids": ["CONF_ADMIN", "CONF_DEV1"]
        },
        created_at=datetime.utcnow()
    )
    
    chunks.extend([slack_chunk, jira_chunk, github_chunk, confluence_chunk])
    
    for chunk in chunks:
        db_session.add(chunk)
    
    db_session.commit()
    
    return chunks


def test_slack_only_user_sees_only_slack(slack_only_user, multi_connector_chunks, db_session):
    """User with only Slack identity should see only Slack results."""
    query = "sprint"
    
    user_dict = {
        "id": slack_only_user.id,
        "email": slack_only_user.email,
        "workspace_id": slack_only_user.workspace_id,
        "connector_identities": slack_only_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should only see the Slack public channel result
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    
    # Verify it's the Slack result
    assert results[0]["connector_type"] == "slack"
    assert results[0]["metadata"]["channel_name"] == "planning"
    
    # Verify Jira, GitHub, Confluence are filtered out
    connector_types = [r["connector_type"] for r in results]
    assert "jira" not in connector_types
    assert "github" not in connector_types
    assert "confluence" not in connector_types


def test_full_access_user_sees_allowed_results(full_access_user, multi_connector_chunks, db_session):
    """User with multiple connector identities sees results from those connectors."""
    query = "sprint"
    
    user_dict = {
        "id": full_access_user.id,
        "email": full_access_user.email,
        "workspace_id": full_access_user.workspace_id,
        "connector_identities": full_access_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should see Slack (public), Jira (has account_id), GitHub (has org membership)
    # Should NOT see Confluence (not in allowed_account_ids)
    assert len(results) == 3, f"Expected 3 results, got {len(results)}"
    
    connector_types = [r["connector_type"] for r in results]
    assert "slack" in connector_types
    assert "jira" in connector_types
    assert "github" in connector_types
    assert "confluence" not in connector_types  # Not authorized


def test_user_without_connector_identities(db_session, multi_connector_chunks):
    """User with no connector identities should only see public content."""
    # Create user with empty connector_identities
    user = User(
        email="new_user@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={}
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    query = "sprint"
    
    user_dict = {
        "id": user.id,
        "email": user.email,
        "workspace_id": user.workspace_id,
        "connector_identities": user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should only see public Slack content
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    assert results[0]["connector_type"] == "slack"
    assert results[0]["acl_json"]["access_level"] == "public"


def test_connector_specific_query(slack_only_user, multi_connector_chunks, db_session):
    """Test that connector-specific queries still respect ACL."""
    # Query specifically for GitHub content
    query = "GitHub authentication service architecture"
    
    user_dict = {
        "id": slack_only_user.id,
        "email": slack_only_user.email,
        "workspace_id": slack_only_user.workspace_id,
        "connector_identities": slack_only_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Even though query matches GitHub content, user shouldn't see it
    # They might see Slack results if they match the query
    for result in results:
        assert result["connector_type"] != "github", \
            "Slack-only user should not see GitHub results"


def test_partial_connector_identity(db_session, multi_connector_chunks):
    """Test user with partial connector identity (Jira but not in allowed list)."""
    user = User(
        email="jira_user@example.com",
        hashed_password="hashed",
        workspace_id=1,
        connector_identities={
            "jira": {
                "account_id": "JIRA_OTHER_USER",  # Not in allowed list
                "email": "jira_user@example.com"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    query = "sprint tasks"
    
    user_dict = {
        "id": user.id,
        "email": user.email,
        "workspace_id": user.workspace_id,
        "connector_identities": user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # User has Jira identity but not in allowed list
    # Should only see public Slack content
    assert len(results) <= 1, "Should see at most the public Slack result"
    
    if len(results) == 1:
        assert results[0]["connector_type"] == "slack"
        assert results[0]["acl_json"]["access_level"] == "public"


def test_mixed_public_and_restricted_results(slack_only_user, db_session):
    """Test that public results from various connectors are visible to all."""
    # Add public results from different connectors
    public_chunks = [
        Chunk(
            chunk_id="slack-public-001",
            connector_type="slack",
            content="Company-wide announcement about product launch",
            embedding=[0.1] * 768,
            workspace_id=1,
            metadata={"channel_name": "announcements", "channel_id": "C_ANNOUNCE"},
            acl_json={
                "connector_type": "slack",
                "access_level": "public"
            },
            created_at=datetime.utcnow()
        ),
        Chunk(
            chunk_id="jira-public-001",
            connector_type="jira",
            content="Product launch roadmap for all teams",
            embedding=[0.11] * 768,
            workspace_id=1,
            metadata={"project_key": "PROD", "issue_key": "PROD-456"},
            acl_json={
                "connector_type": "jira",
                "access_level": "public",
                "project_visibility": "public"
            },
            created_at=datetime.utcnow()
        ),
        Chunk(
            chunk_id="github-public-001",
            connector_type="github",
            content="Product launch documentation in public repo",
            embedding=[0.12] * 768,
            workspace_id=1,
            metadata={"repo_name": "docs", "file_path": "launch.md"},
            acl_json={
                "connector_type": "github",
                "access_level": "public",
                "repo_visibility": "public"
            },
            created_at=datetime.utcnow()
        )
    ]
    
    for chunk in public_chunks:
        db_session.add(chunk)
    db_session.commit()
    
    query = "product launch"
    
    user_dict = {
        "id": slack_only_user.id,
        "email": slack_only_user.email,
        "workspace_id": slack_only_user.workspace_id,
        "connector_identities": slack_only_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Should see all 3 public results regardless of connector type
    assert len(results) == 3, f"Expected 3 public results, got {len(results)}"
    
    connector_types = [r["connector_type"] for r in results]
    assert "slack" in connector_types
    assert "jira" in connector_types
    assert "github" in connector_types
    
    # Verify all are public
    for result in results:
        assert result["acl_json"]["access_level"] == "public"


def test_no_results_when_all_restricted(slack_only_user, db_session):
    """Test that user sees no results when all matching content is restricted."""
    # Add only restricted content from non-Slack connectors
    restricted_chunks = [
        Chunk(
            chunk_id="jira-restricted-001",
            connector_type="jira",
            content="Secret project details for core team only",
            embedding=[0.1] * 768,
            workspace_id=1,
            metadata={"project_key": "SECRET", "issue_key": "SECRET-123"},
            acl_json={
                "connector_type": "jira",
                "access_level": "restricted",
                "allowed_account_ids": ["JIRA_ADMIN"]
            },
            created_at=datetime.utcnow()
        ),
        Chunk(
            chunk_id="github-private-001",
            connector_type="github",
            content="Secret project implementation code",
            embedding=[0.11] * 768,
            workspace_id=1,
            metadata={"repo_name": "secret-project", "file_path": "src/main.py"},
            acl_json={
                "connector_type": "github",
                "access_level": "restricted",
                "repo_visibility": "private",
                "collaborators": ["admin-user"]
            },
            created_at=datetime.utcnow()
        )
    ]
    
    for chunk in restricted_chunks:
        db_session.add(chunk)
    db_session.commit()
    
    query = "secret project"
    
    user_dict = {
        "id": slack_only_user.id,
        "email": slack_only_user.email,
        "workspace_id": slack_only_user.workspace_id,
        "connector_identities": slack_only_user.connector_identities
    }
    
    results = hybrid_search(
        query=query,
        workspace_id=1,
        user=user_dict,
        top_k=10
    )
    
    # Slack-only user should see no results (all are restricted Jira/GitHub)
    assert len(results) == 0, f"Expected 0 results, got {len(results)}"
