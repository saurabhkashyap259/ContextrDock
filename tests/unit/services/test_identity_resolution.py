"""Tests for email-based identity resolution."""

import pytest
from sqlalchemy.orm import Session

from src.models.user import User
from src.services.identity_resolution import resolve_user_identities


def test_resolve_user_identities_returns_all_identities(db_session: Session) -> None:
    """Test that all user identities are returned."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={
            "slack": {"external_id": "U12345", "email": "user@example.com"},
            "jira": {"external_id": "accountId123", "email": "user@example.com"},
        },
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(db_session, user.id)
    
    assert len(identities) == 2
    
    # Check Slack identity
    slack_identity = next(i for i in identities if i["connector_type"] == "slack")
    assert slack_identity["email"] == "user@example.com"
    assert slack_identity["external_id"] == "U12345"
    
    # Check Jira identity
    jira_identity = next(i for i in identities if i["connector_type"] == "jira")
    assert jira_identity["email"] == "user@example.com"
    assert jira_identity["external_id"] == "accountId123"


def test_resolve_user_identities_includes_channels(db_session: Session) -> None:
    """Test that channel memberships are included."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={
            "slack": {
                "external_id": "U12345",
                "email": "user@example.com",
                "channels": ["C123", "C456", "C789"],
            },
        },
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(db_session, user.id)
    
    slack_identity = identities[0]
    assert "channels" in slack_identity
    assert slack_identity["channels"] == ["C123", "C456", "C789"]


def test_resolve_user_identities_empty_when_no_connector_identities(db_session: Session) -> None:
    """Test empty list when user has no connector identities."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={},  # Empty
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(db_session, user.id)
    
    assert identities == []


def test_resolve_user_identities_handles_null_connector_identities(db_session: Session) -> None:
    """Test handling of null connector_identities field."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities=None,  # Null
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(db_session, user.id)
    
    assert identities == []


def test_resolve_user_identities_includes_all_fields(db_session: Session) -> None:
    """Test that all identity fields are preserved."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={
            "github": {
                "external_id": "123456",
                "email": "user@example.com",
                "username": "userhandle",
                "organizations": ["org1", "org2"],
            },
        },
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(db_session, user.id)
    
    github_identity = identities[0]
    assert github_identity["connector_type"] == "github"
    assert github_identity["external_id"] == "123456"
    assert github_identity["email"] == "user@example.com"
    assert github_identity["username"] == "userhandle"
    assert github_identity["organizations"] == ["org1", "org2"]


def test_resolve_user_identities_user_not_found(db_session: Session) -> None:
    """Test that None is returned when user doesn't exist."""
    identities = resolve_user_identities(db_session, user_id=99999)
    
    assert identities is None


def test_resolve_user_identities_by_email(db_session: Session) -> None:
    """Test resolving identities by email address."""
    user = User(
        workspace_id=1,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={
            "slack": {"external_id": "U12345", "email": "user@example.com"},
        },
    )
    db_session.add(user)
    db_session.commit()
    
    identities = resolve_user_identities(
        db_session,
        email="user@example.com",
        workspace_id=1,
    )
    
    assert len(identities) == 1
    assert identities[0]["connector_type"] == "slack"


def test_resolve_user_identities_by_email_not_found(db_session: Session) -> None:
    """Test that None is returned when email doesn't match any user."""
    identities = resolve_user_identities(
        db_session,
        email="nonexistent@example.com",
        workspace_id=1,
    )
    
    assert identities is None


def test_resolve_user_identities_requires_user_id_or_email(db_session: Session) -> None:
    """Test that either user_id or (email + workspace_id) is required."""
    with pytest.raises(ValueError, match="Either user_id or both email and workspace_id must be provided"):
        resolve_user_identities(db_session)


def test_resolve_user_identities_email_requires_workspace_id(db_session: Session) -> None:
    """Test that email lookup requires workspace_id."""
    with pytest.raises(ValueError, match="Either user_id or both email and workspace_id must be provided"):
        resolve_user_identities(db_session, email="user@example.com")
