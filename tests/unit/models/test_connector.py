"""Tests for Connector model."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document
from src.models.sync_run import SyncRun
from src.models.workspace import Workspace


def test_connector_model_creation(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test creating a connector with required fields."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Engineering Slack",
        config_json={"team_id": "T123456"},
        credentials_encrypted=b"encrypted_token_here",
        sync_schedule="0 */6 * * *",  # Every 6 hours
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    
    assert connector.id is not None
    assert connector.workspace_id == workspace.id
    assert connector.name == "Engineering Slack"
    assert connector.is_active is True


def test_connector_model_with_null_credentials(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test connector can have null credentials (for setup state)."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Pending Connector",
        config_json={},
        credentials_encrypted=None,  # Not yet configured
        sync_schedule=None,
        is_active=False,
    )
    db_session.add(connector)
    db_session.commit()
    
    assert connector.credentials_encrypted is None
    assert connector.is_active is False


def test_connector_model_config_json_field(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test config_json stores arbitrary configuration."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    config = {
        "base_url": "https://company.slack.com",
        "team_id": "T123456",
        "channels": ["general", "engineering"],
        "include_private": False,
    }
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Slack",
        config_json=config,
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    db_session.commit()
    
    retrieved = db_session.query(Connector).filter(Connector.id == connector.id).first()
    assert retrieved.config_json == config
    assert retrieved.config_json["team_id"] == "T123456"
    assert retrieved.config_json["channels"] == ["general", "engineering"]


def test_connector_model_sync_schedule_cron(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test various cron schedule formats."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    schedules = [
        "0 */6 * * *",  # Every 6 hours
        "0 0 * * *",    # Daily at midnight
        "*/15 * * * *", # Every 15 minutes
        "0 9-17 * * 1-5", # Weekdays 9am-5pm
    ]
    
    for schedule in schedules:
        connector = Connector(
            workspace_id=workspace.id,
            connector_definition_id=test_connector_definition.id,
            name=f"Connector {schedule}",
            config_json={},
            credentials_encrypted=b"token",
            sync_schedule=schedule,
        )
        db_session.add(connector)
    
    db_session.commit()
    
    # Query only connectors for this workspace
    connectors = db_session.query(Connector).filter(Connector.workspace_id == workspace.id).all()
    assert len(connectors) == 4


def test_connector_model_timestamps(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test created_at and updated_at timestamps."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    db_session.commit()
    
    assert connector.created_at is not None
    assert connector.updated_at is not None
    assert connector.created_at == connector.updated_at
    
    # Update connector
    original_updated_at = connector.updated_at
    connector.name = "Updated Name"
    db_session.commit()
    
    assert connector.updated_at > original_updated_at


def test_connector_model_last_synced_at(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test last_synced_at tracking."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    db_session.commit()
    
    assert connector.last_synced_at is None  # Never synced
    
    # Simulate sync
    connector.last_synced_at = datetime.utcnow()
    db_session.commit()
    
    assert connector.last_synced_at is not None


def test_connector_model_workspace_relationship(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test relationship between Connector and Workspace."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    db_session.commit()
    
    # Access workspace through relationship
    assert connector.workspace.id == workspace.id
    assert connector.workspace.name == "Test Workspace"


def test_connector_model_requires_workspace_id(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test that workspace_id is required."""
    connector = Connector(
        workspace_id=None,  # Missing
        connector_definition_id=test_connector_definition.id,
        name="Invalid Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_connector_model_is_active_default(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test is_active defaults to True."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
    )
    db_session.add(connector)
    db_session.commit()
    
    assert connector.is_active is True


def test_connector_model_cursor_state_json(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test cursor_state_json for incremental sync."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    cursor_state = {
        "last_message_ts": "1234567890.123456",
        "channel_cursors": {
            "C123": "cursor_abc",
            "C456": "cursor_xyz",
        },
        "last_updated_user": "2024-01-15T10:00:00Z",
    }
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Slack Connector",
        config_json={},
        credentials_encrypted=b"token",
        sync_schedule="0 0 * * *",
        cursor_state_json=cursor_state,
    )
    db_session.add(connector)
    db_session.commit()
    
    retrieved = db_session.query(Connector).filter(Connector.id == connector.id).first()
    assert retrieved.cursor_state_json == cursor_state
    assert retrieved.cursor_state_json["last_message_ts"] == "1234567890.123456"
