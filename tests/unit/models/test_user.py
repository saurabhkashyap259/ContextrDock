"""Tests for User model."""

import pytest
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.workspace import Workspace


def test_user_creation(db_session: Session) -> None:
    """Test creating a user with required fields."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    user = User(
        workspace_id=workspace.id,
        email="test@example.com",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.role == "user"
    assert user.workspace_id == workspace.id
    assert user.connector_identities == {}
    assert user.created_at is not None


def test_user_email_required(db_session: Session) -> None:
    """Test that email is required."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    user = User(workspace_id=workspace.id, role="user")
    db_session.add(user)
    
    with pytest.raises(Exception):  # Will raise IntegrityError
        db_session.commit()


def test_user_connector_identities_json(db_session: Session) -> None:
    """Test that connector_identities stores JSON correctly."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    identities = {
        "slack": "U123456",
        "jira": "account-id-123",
        "github": "testuser",
    }
    
    user = User(
        workspace_id=workspace.id,
        email="test@example.com",
        role="user",
        connector_identities=identities,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    assert user.connector_identities == identities
    assert user.connector_identities["slack"] == "U123456"


def test_user_default_role(db_session: Session) -> None:
    """Test that default role is 'user'."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    user = User(
        workspace_id=workspace.id,
        email="test@example.com",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    assert user.role == "user"
