"""End-to-end test for US2 Scenario 3: View connector status."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

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
def connectors_with_various_states(db_session: Session):
    """Create connectors in various states for status viewing."""
    now = datetime.utcnow()
    
    # Connector 1: Active with successful syncs
    connector1 = Connector(
        workspace_id=1,
        connector_type="slack",
        display_name="Active Slack",
        config={"team_id": "T123"},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */3 * * *",
        is_active=True,
    )
    db_session.add(connector1)
    db_session.commit()
    db_session.refresh(connector1)
    
    syncs1 = [
        SyncRun(
            connector_id=connector1.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6, minutes=-10),
            documents_added=100,
            documents_updated=20,
        ),
        SyncRun(
            connector_id=connector1.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=3, minutes=-8),
            documents_added=15,
            documents_updated=25,
        ),
    ]
    for sync in syncs1:
        db_session.add(sync)
    
    # Connector 2: Active with recent failure
    connector2 = Connector(
        workspace_id=1,
        connector_type="jira",
        display_name="Failing Jira",
        config={"cloud_id": "abc"},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */6 * * *",
        is_active=True,
    )
    db_session.add(connector2)
    db_session.commit()
    db_session.refresh(connector2)
    
    syncs2 = [
        SyncRun(
            connector_id=connector2.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(days=1),
            completed_at=now - timedelta(days=1, minutes=-12),
            documents_added=50,
        ),
        SyncRun(
            connector_id=connector2.id,
            status=SyncStatus.FAILED.value,
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1, minutes=-2),
            error_message="Authentication failed: Invalid credentials",
        ),
    ]
    for sync in syncs2:
        db_session.add(sync)
    
    # Connector 3: Currently running
    connector3 = Connector(
        workspace_id=1,
        connector_type="github",
        display_name="Running GitHub",
        config={"org": "myorg"},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 0 * * *",
        is_active=True,
    )
    db_session.add(connector3)
    db_session.commit()
    db_session.refresh(connector3)
    
    syncs3 = [
        SyncRun(
            connector_id=connector3.id,
            status=SyncStatus.RUNNING.value,
            started_at=now - timedelta(minutes=5),
        ),
    ]
    for sync in syncs3:
        db_session.add(sync)
    
    # Connector 4: Inactive, never synced
    connector4 = Connector(
        workspace_id=1,
        connector_type="figma",
        display_name="Inactive Figma",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=False,
    )
    db_session.add(connector4)
    db_session.commit()
    db_session.refresh(connector4)
    
    db_session.commit()
    
    return {
        "active_success": connector1,
        "active_failed": connector2,
        "running": connector3,
        "inactive": connector4,
    }


def test_us2_scenario3_view_connector_status_overview(
    client, connectors_with_various_states
):
    """
    US2 Scenario 3: View connector status overview
    
    Steps:
    1. List all connectors
    2. View individual connector details
    3. Check sync history
    4. Verify status indicators
    """
    # Step 1: List all connectors
    list_response = client.get("/v1/connectors")
    
    assert list_response.status_code == 200
    data = list_response.json()
    
    assert data["total"] == 4
    assert len(data["connectors"]) == 4
    
    # Check we have different statuses
    statuses = {c["last_sync_status"] for c in data["connectors"]}
    assert "completed" in statuses
    assert "failed" in statuses
    assert "running" in statuses
    
    print("✅ US2 Scenario 3: View connector status overview - PASSED")


def test_us2_scenario3_active_successful_connector(
    client, connectors_with_various_states
):
    """View status of active connector with successful syncs."""
    connector = connectors_with_various_states["active_success"]
    
    # Get connector details
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_active"] is True
    assert data["last_sync_status"] == "completed"
    assert data["last_sync_at"] is not None
    assert len(data["recent_sync_runs"]) == 2
    
    # All syncs successful
    for run in data["recent_sync_runs"]:
        assert run["status"] == "completed"
        assert run["documents_added"] > 0
    
    # Get full sync history
    history = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    assert history.status_code == 200
    
    history_data = history.json()
    assert history_data["total"] == 2
    
    # Calculate total documents
    total_added = sum(run["documents_added"] for run in history_data["sync_runs"])
    assert total_added == 115  # 100 + 15


def test_us2_scenario3_failed_connector(client, connectors_with_various_states):
    """View status of connector with recent failure."""
    connector = connectors_with_various_states["active_failed"]
    
    # Get connector details
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_active"] is True
    assert data["last_sync_status"] == "failed"
    assert len(data["recent_sync_runs"]) == 2
    
    # Most recent sync failed
    latest_run = data["recent_sync_runs"][0]
    assert latest_run["status"] == "failed"
    assert latest_run["error_message"] is not None
    assert "Authentication failed" in latest_run["error_message"]
    
    # Get failed sync details
    history = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?status=failed"
    )
    assert history.status_code == 200
    
    failed_data = history.json()
    assert failed_data["total"] == 1
    assert failed_data["sync_runs"][0]["error_message"] == "Authentication failed: Invalid credentials"


def test_us2_scenario3_running_connector(client, connectors_with_various_states):
    """View status of connector with sync currently running."""
    connector = connectors_with_various_states["running"]
    
    # Get connector details
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_active"] is True
    assert data["last_sync_status"] == "running"
    assert len(data["recent_sync_runs"]) == 1
    
    # Running sync details
    running_sync = data["recent_sync_runs"][0]
    assert running_sync["status"] == "running"
    assert running_sync["completed_at"] is None
    assert running_sync["started_at"] is not None
    
    # No documents counted yet
    assert running_sync["documents_added"] == 0
    assert running_sync["documents_updated"] == 0


def test_us2_scenario3_inactive_never_synced(
    client, connectors_with_various_states
):
    """View status of inactive connector that never synced."""
    connector = connectors_with_various_states["inactive"]
    
    # Get connector details
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_active"] is False
    assert data["last_sync_status"] is None
    assert data["last_sync_at"] is None
    assert len(data["recent_sync_runs"]) == 0
    
    # Get sync history
    history = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    assert history.status_code == 200
    
    history_data = history.json()
    assert history_data["total"] == 0
    assert len(history_data["sync_runs"]) == 0


def test_us2_scenario3_filter_by_active_status(
    client, connectors_with_various_states
):
    """Filter connectors by active status."""
    # Get only active connectors
    response = client.get("/v1/connectors?is_active=true")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3
    assert all(c["is_active"] for c in data["connectors"])
    
    # Get only inactive connectors
    response = client.get("/v1/connectors?is_active=false")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert not data["connectors"][0]["is_active"]


def test_us2_scenario3_sync_history_pagination(
    client, connectors_with_various_states
):
    """View paginated sync history."""
    connector = connectors_with_various_states["active_success"]
    
    # Get first page
    response = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?page=1&page_size=1"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2
    assert len(data["sync_runs"]) == 1
    assert data["page"] == 1
    assert data["page_size"] == 1
    
    # Get second page
    response = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?page=2&page_size=1"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2
    assert len(data["sync_runs"]) == 1
    assert data["page"] == 2


def test_us2_scenario3_sync_metrics_summary(
    client, connectors_with_various_states
):
    """View sync metrics summary across all runs."""
    connector = connectors_with_various_states["active_success"]
    
    # Get all sync runs
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Calculate totals
    total_added = sum(run["documents_added"] for run in data["sync_runs"])
    total_updated = sum(run["documents_updated"] for run in data["sync_runs"])
    
    assert total_added == 115  # 100 + 15
    assert total_updated == 45  # 20 + 25
    
    # All completed successfully
    completed_count = sum(
        1 for run in data["sync_runs"] if run["status"] == "completed"
    )
    assert completed_count == 2
