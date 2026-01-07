"""Integration tests for GET /v1/connectors/{id}/sync-runs endpoint."""

import pytest
from datetime import datetime, timedelta
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
def sample_connector_with_runs(db_session: Session):
    """Create connector with multiple sync runs."""
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
    
    # Create sync runs with different statuses and times
    now = datetime.utcnow()
    sync_runs = [
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6, minutes=-10),
            documents_added=15,
            documents_updated=3,
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=3, minutes=-8),
            documents_added=8,
            documents_updated=2,
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.FAILED.value,
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1, minutes=-2),
            error_message="Rate limit exceeded",
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.RUNNING.value,
            started_at=now - timedelta(minutes=5),
        ),
    ]
    
    for sync_run in sync_runs:
        db_session.add(sync_run)
    db_session.commit()
    
    for sync_run in sync_runs:
        db_session.refresh(sync_run)
    
    return connector


def test_list_sync_runs_success(client, sample_connector_with_runs):
    """Test successful list of sync runs."""
    response = client.get(f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 4
    assert len(data["sync_runs"]) == 4
    assert data["page"] == 1
    assert data["page_size"] == 50
    
    # Check they're ordered by started_at desc (newest first)
    statuses = [run["status"] for run in data["sync_runs"]]
    assert statuses[0] == "running"  # Most recent
    assert statuses[-1] == "completed"  # Oldest


def test_list_sync_runs_pagination(client, sample_connector_with_runs):
    """Test pagination of sync runs."""
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?page=1&page_size=2"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 4
    assert len(data["sync_runs"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2
    
    # Get second page
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?page=2&page_size=2"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 4
    assert len(data["sync_runs"]) == 2
    assert data["page"] == 2


def test_list_sync_runs_filter_by_status(client, sample_connector_with_runs):
    """Test filtering by sync status."""
    # Get only completed syncs
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?status=completed"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2
    assert all(run["status"] == "completed" for run in data["sync_runs"])
    
    # Get only failed syncs
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?status=failed"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert data["sync_runs"][0]["status"] == "failed"
    assert "Rate limit" in data["sync_runs"][0]["error_message"]


def test_list_sync_runs_running_status(client, sample_connector_with_runs):
    """Test filtering for running syncs."""
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?status=running"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert data["sync_runs"][0]["status"] == "running"
    assert data["sync_runs"][0]["completed_at"] is None


def test_list_sync_runs_connector_not_found(client):
    """Test list sync runs for non-existent connector."""
    response = client.get("/v1/connectors/99999/sync-runs")
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_list_sync_runs_wrong_workspace(client, db_session: Session):
    """Test list sync runs for connector in different workspace."""
    connector = Connector(
        workspace_id=2,
        connector_type="jira",
        display_name="Other Team",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 404


def test_list_sync_runs_empty(client, db_session: Session):
    """Test list sync runs for connector with no runs."""
    connector = Connector(
        workspace_id=1,
        connector_type="github",
        display_name="Org GitHub",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0
    assert len(data["sync_runs"]) == 0


def test_list_sync_runs_includes_all_fields(client, sample_connector_with_runs):
    """Test that sync run response includes all expected fields."""
    response = client.get(f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    sync_run = data["sync_runs"][0]
    
    # Check all fields present
    assert "id" in sync_run
    assert "connector_id" in sync_run
    assert "status" in sync_run
    assert "started_at" in sync_run
    # completed_at might be None for running syncs
    assert "documents_added" in sync_run
    assert "documents_updated" in sync_run
    assert "documents_deleted" in sync_run
    # error_message and cursor_state might be None


def test_list_sync_runs_order_newest_first(client, sample_connector_with_runs):
    """Test that sync runs are ordered by started_at descending."""
    response = client.get(f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Parse timestamps and verify order
    timestamps = [
        datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
        for run in data["sync_runs"]
    ]
    
    # Should be in descending order (newest first)
    for i in range(len(timestamps) - 1):
        assert timestamps[i] >= timestamps[i + 1]


def test_list_sync_runs_with_large_page_size(client, sample_connector_with_runs):
    """Test requesting large page size."""
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?page_size=100"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should cap at max allowed (100)
    assert data["page_size"] == 100
    assert len(data["sync_runs"]) == 4  # All available


def test_list_sync_runs_invalid_page(client, sample_connector_with_runs):
    """Test invalid page number."""
    response = client.get(
        f"/v1/connectors/{sample_connector_with_runs.id}/sync-runs?page=0"
    )
    
    # Should return validation error
    assert response.status_code == 422
