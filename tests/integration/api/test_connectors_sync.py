"""Integration tests for POST /v1/connectors/{id}/sync endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.connectors import router
from src.models.connector import Connector
from src.models.sync_run import SyncRun, SyncStatus
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app with connector routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_connector(db_session: Session):
    """Create a sample connector for testing."""
    connector = Connector(
        workspace_id=1,
        connector_type="slack",
        display_name="Team Slack",
        config={"team_id": "T123"},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    return connector


@patch("src.api.routes.connectors.run_connector_sync")
def test_trigger_sync_success(mock_task, client, sample_connector, db_session: Session):
    """Test successful sync trigger."""
    # Mock Celery task result
    mock_result = MagicMock()
    mock_result.id = "task-123"
    mock_task.delay.return_value = mock_result
    
    # Create a sync run that the task would create
    sync_run = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    response = client.post(f"/v1/connectors/{sample_connector.id}/sync")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "sync_run_id" in data
    assert data["status"] == "queued"
    assert "task_id" in data["message"]
    
    # Verify Celery task was called
    mock_task.delay.assert_called_once_with(sample_connector.id)


@patch("src.api.routes.connectors.run_connector_sync")
def test_trigger_sync_with_force(mock_task, client, sample_connector, db_session: Session):
    """Test sync trigger with force flag."""
    mock_result = MagicMock()
    mock_result.id = "task-456"
    mock_task.delay.return_value = mock_result
    
    # Create existing running sync
    existing_sync = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(existing_sync)
    db_session.commit()
    
    payload = {"force": True}
    
    response = client.post(f"/v1/connectors/{sample_connector.id}/sync", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "queued"
    
    # Should have called task despite running sync
    mock_task.delay.assert_called_once_with(sample_connector.id)


def test_trigger_sync_already_running(client, sample_connector, db_session: Session):
    """Test sync trigger when sync already running."""
    # Create running sync
    sync_run = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    response = client.post(f"/v1/connectors/{sample_connector.id}/sync")
    
    assert response.status_code == 409  # Conflict
    data = response.json()
    assert "already in progress" in data["detail"].lower()


def test_trigger_sync_connector_inactive(client, db_session: Session):
    """Test sync trigger on inactive connector."""
    connector = Connector(
        workspace_id=1,
        connector_type="jira",
        display_name="Inactive Jira",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=False,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    response = client.post(f"/v1/connectors/{connector.id}/sync")
    
    assert response.status_code == 400
    data = response.json()
    assert "not active" in data["detail"].lower()


def test_trigger_sync_connector_not_found(client):
    """Test sync trigger on non-existent connector."""
    response = client.post("/v1/connectors/99999/sync")
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_trigger_sync_wrong_workspace(client, db_session: Session):
    """Test sync trigger on connector from different workspace."""
    connector = Connector(
        workspace_id=2,
        connector_type="slack",
        display_name="Other Team",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    response = client.post(f"/v1/connectors/{connector.id}/sync")
    
    assert response.status_code == 404


@patch("src.api.routes.connectors.run_connector_sync")
def test_trigger_sync_default_force_false(mock_task, client, sample_connector, db_session: Session):
    """Test sync trigger without force parameter defaults to false."""
    mock_result = MagicMock()
    mock_result.id = "task-789"
    mock_task.delay.return_value = mock_result
    
    # Create new sync run
    sync_run = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    # No force parameter
    response = client.post(f"/v1/connectors/{sample_connector.id}/sync", json={})
    
    # Should conflict
    assert response.status_code == 409


@patch("src.api.routes.connectors.run_connector_sync")
def test_trigger_sync_after_completed_sync(mock_task, client, sample_connector, db_session: Session):
    """Test sync trigger after previous sync completed."""
    mock_result = MagicMock()
    mock_result.id = "task-completed"
    mock_task.delay.return_value = mock_result
    
    # Create completed sync
    sync_run = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.COMPLETED.value,
        documents_added=10,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    # Create new sync run for the new trigger
    new_sync = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(new_sync)
    db_session.commit()
    
    response = client.post(f"/v1/connectors/{sample_connector.id}/sync")
    
    # Should succeed (previous sync not running)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"


@patch("src.api.routes.connectors.run_connector_sync")
def test_trigger_sync_multiple_connectors(mock_task, client, db_session: Session):
    """Test triggering sync on multiple connectors."""
    mock_result = MagicMock()
    mock_result.id = "task-multi"
    mock_task.delay.return_value = mock_result
    
    # Create multiple connectors
    connectors = []
    for i in range(3):
        connector = Connector(
            workspace_id=1,
            connector_type="slack",
            display_name=f"Slack {i}",
            config={},
            credentials_encrypted=b"encrypted",
            is_active=True,
        )
        db_session.add(connector)
        connectors.append(connector)
    
    db_session.commit()
    
    # Trigger sync on each
    for connector in connectors:
        db_session.refresh(connector)
        
        # Create sync run for each
        sync_run = SyncRun(
            connector_id=connector.id,
            status=SyncStatus.RUNNING.value,
        )
        db_session.add(sync_run)
        db_session.commit()
        
        response = client.post(f"/v1/connectors/{connector.id}/sync")
        assert response.status_code == 200
    
    # Verify task called for each
    assert mock_task.delay.call_count == 3
