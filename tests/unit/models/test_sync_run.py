"""Tests for SyncRun model."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from src.models.sync_run import SyncRun
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document
from src.models.workspace import Workspace


def test_sync_run_model_creation(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test creating a sync run."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="running",
        started_at=datetime.utcnow(),
    )
    db_session.add(sync_run)
    db_session.commit()
    
    assert sync_run.id is not None
    assert sync_run.connector_id == connector.id
    assert sync_run.status == "running"


def test_sync_run_model_status_lifecycle(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test sync run status transitions."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    # Start sync
    sync_run = SyncRun(
        connector_id=connector.id,
        status="running",
        started_at=datetime.utcnow(),
    )
    db_session.add(sync_run)
    db_session.commit()
    
    assert sync_run.status == "running"
    assert sync_run.completed_at is None
    
    # Complete sync
    sync_run.status = "completed"
    sync_run.completed_at = datetime.utcnow()
    sync_run.documents_added = 150
    sync_run.documents_updated = 25
    sync_run.documents_deleted = 5
    db_session.commit()
    
    assert sync_run.status == "completed"
    assert sync_run.completed_at is not None
    assert sync_run.documents_added == 150


def test_sync_run_model_failed_status(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test sync run with failed status."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="failed",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        error_message="API rate limit exceeded",
    )
    db_session.add(sync_run)
    db_session.commit()
    
    assert sync_run.status == "failed"
    assert sync_run.error_message == "API rate limit exceeded"


def test_sync_run_model_document_counts(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test document count tracking."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="completed",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        documents_added=100,
        documents_updated=50,
        documents_deleted=10,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    assert sync_run.documents_added == 100
    assert sync_run.documents_updated == 50
    assert sync_run.documents_deleted == 10


def test_sync_run_model_cursor_state_json(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test cursor state for incremental sync."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    cursor_state = {
        "next_page_token": "abc123",
        "last_processed_id": "msg-789",
        "channel_cursors": {
            "C123": "cursor_1",
            "C456": "cursor_2",
        },
    }
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="completed",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        cursor_state_json=cursor_state,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    retrieved = db_session.query(SyncRun).filter(SyncRun.id == sync_run.id).first()
    assert retrieved.cursor_state_json == cursor_state
    assert retrieved.cursor_state_json["next_page_token"] == "abc123"


def test_sync_run_model_duration_calculation(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test calculating sync duration."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    started = datetime.utcnow()
    completed = started + timedelta(minutes=5, seconds=30)
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="completed",
        started_at=started,
        completed_at=completed,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    # Duration can be calculated from timestamps
    duration = (sync_run.completed_at - sync_run.started_at).total_seconds()
    assert duration == 330.0  # 5 minutes 30 seconds


def test_sync_run_model_relationship_with_connector(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test relationship between SyncRun and Connector."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="completed",
        started_at=datetime.utcnow(),
    )
    db_session.add(sync_run)
    db_session.commit()
    
    # Access connector through relationship
    assert sync_run.connector.id == connector.id
    assert sync_run.connector.name == "Test Connector"
    
    # Access sync runs from connector
    assert len(connector.sync_runs) == 1
    assert connector.sync_runs[0].id == sync_run.id


def test_sync_run_model_multiple_runs_per_connector(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test multiple sync runs for same connector."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    # Create multiple sync runs
    now = datetime.now(timezone.utc)
    for i in range(5):
        # i=0 is the most recent (now), so it should be "running"
        # i=1,2,3,4 are older runs (now - 1hr, 2hr, 3hr, 4hr), so they should be "completed"
        sync_run = SyncRun(
            connector_id=connector.id,
            status="running" if i == 0 else "completed",
            started_at=now - timedelta(hours=i),
            completed_at=now - timedelta(hours=i, minutes=-30) if i > 0 else None,
        )
        db_session.add(sync_run)
    
    db_session.commit()
    
    # Verify all runs exist
    runs = db_session.query(SyncRun).filter(SyncRun.connector_id == connector.id).all()
    assert len(runs) == 5
    
    # Most recent run should be "running"
    latest_run = max(runs, key=lambda r: r.started_at)
    assert latest_run.status == "running"


def test_sync_run_model_timestamps(db_session: Session, test_connector_definition: ConnectorDefinition) -> None:
    """Test created_at timestamp."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    connector = Connector(
        workspace_id=workspace.id,
        connector_definition_id=test_connector_definition.id,
        name="Test Connector",
        config_json={},
        credentials_encrypted=b"token",
    )
    db_session.add(connector)
    db_session.flush()
    
    sync_run = SyncRun(
        connector_id=connector.id,
        status="running",
        started_at=datetime.utcnow(),
    )
    db_session.add(sync_run)
    db_session.commit()
    
    assert sync_run.created_at is not None
