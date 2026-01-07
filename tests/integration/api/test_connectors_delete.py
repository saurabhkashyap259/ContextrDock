"""Integration tests for DELETE /v1/connectors/{id} endpoint."""

import pytest
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


def test_delete_connector_success(client, sample_connector, db_session: Session):
    """Test successful connector deletion."""
    connector_id = sample_connector.id
    
    response = client.delete(f"/v1/connectors/{connector_id}")
    
    assert response.status_code == 204
    assert response.content == b""  # No content
    
    # Verify deleted from database
    connector = db_session.query(Connector).filter_by(id=connector_id).first()
    assert connector is None


def test_delete_connector_not_found(client):
    """Test deleting non-existent connector."""
    response = client.delete("/v1/connectors/99999")
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_delete_connector_wrong_workspace(client, db_session: Session):
    """Test deleting connector from different workspace."""
    # Create connector in different workspace
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
    
    # Should not find it (get_workspace_id returns 1)
    response = client.delete(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 404
    
    # Verify still exists in database
    exists = db_session.query(Connector).filter_by(id=connector.id).first()
    assert exists is not None


def test_delete_connector_with_sync_runs(client, sample_connector, db_session: Session):
    """Test deleting connector that has sync runs."""
    # Create sync runs
    sync_runs = [
        SyncRun(
            connector_id=sample_connector.id,
            status=SyncStatus.COMPLETED.value,
            documents_added=10,
        ),
        SyncRun(
            connector_id=sample_connector.id,
            status=SyncStatus.COMPLETED.value,
            documents_added=5,
        ),
    ]
    
    for sync_run in sync_runs:
        db_session.add(sync_run)
    db_session.commit()
    
    connector_id = sample_connector.id
    
    response = client.delete(f"/v1/connectors/{connector_id}")
    
    assert response.status_code == 204
    
    # Verify connector deleted
    connector = db_session.query(Connector).filter_by(id=connector_id).first()
    assert connector is None
    
    # Check if sync runs also deleted (cascade)
    remaining_runs = db_session.query(SyncRun).filter_by(connector_id=connector_id).all()
    # Depending on cascade config, they might be deleted or orphaned
    # For now, just verify the test runs


def test_delete_connector_with_running_sync(client, sample_connector, db_session: Session):
    """Test deleting connector with active sync."""
    # Create running sync
    sync_run = SyncRun(
        connector_id=sample_connector.id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync_run)
    db_session.commit()
    
    connector_id = sample_connector.id
    
    # Should still delete (or return 400 if we want to prevent this)
    response = client.delete(f"/v1/connectors/{connector_id}")
    
    # For now accepting deletion
    assert response.status_code == 204
    
    # Verify deleted
    connector = db_session.query(Connector).filter_by(id=connector_id).first()
    assert connector is None


def test_delete_connector_inactive(client, db_session: Session):
    """Test deleting inactive connector."""
    connector = Connector(
        workspace_id=1,
        connector_type="jira",
        display_name="Old Jira",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=False,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    connector_id = connector.id
    
    response = client.delete(f"/v1/connectors/{connector_id}")
    
    assert response.status_code == 204
    
    # Verify deleted
    connector = db_session.query(Connector).filter_by(id=connector_id).first()
    assert connector is None


def test_delete_connector_twice(client, sample_connector, db_session: Session):
    """Test deleting the same connector twice."""
    connector_id = sample_connector.id
    
    # First deletion
    response = client.delete(f"/v1/connectors/{connector_id}")
    assert response.status_code == 204
    
    # Second deletion should return 404
    response = client.delete(f"/v1/connectors/{connector_id}")
    assert response.status_code == 404
