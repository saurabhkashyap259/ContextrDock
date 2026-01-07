"""Tests for Workspace model."""

import pytest
from sqlalchemy.orm import Session

from src.models.workspace import Workspace


def test_workspace_creation(db_session: Session) -> None:
    """Test creating a workspace with required fields."""
    workspace = Workspace(
        name="Test Company",
    )
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)

    assert workspace.id is not None
    assert workspace.name == "Test Company"
    assert workspace.created_at is not None
    assert workspace.updated_at is not None


def test_workspace_name_required(db_session: Session) -> None:
    """Test that workspace name is required."""
    workspace = Workspace()
    db_session.add(workspace)
    
    with pytest.raises(Exception):  # Will raise IntegrityError
        db_session.commit()


def test_workspace_timestamps(db_session: Session) -> None:
    """Test that timestamps are automatically set."""
    workspace = Workspace(name="Timestamp Test")
    db_session.add(workspace)
    db_session.commit()
    
    created_at = workspace.created_at
    updated_at = workspace.updated_at
    
    assert created_at is not None
    assert updated_at is not None
    assert created_at == updated_at
    
    # Update the workspace
    workspace.name = "Updated Name"
    db_session.commit()
    db_session.refresh(workspace)
    
    assert workspace.updated_at > updated_at
    assert workspace.created_at == created_at
