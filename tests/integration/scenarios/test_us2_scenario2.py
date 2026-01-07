"""End-to-end test for US2 Scenario 2: Manual sync now."""

import pytest
from unittest.mock import patch, MagicMock
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
def existing_connector(db_session: Session):
    """Create an existing connector with previous sync history."""
    connector = Connector(
        workspace_id=1,
        connector_type="jira",
        display_name="Project Tracker",
        config={"cloud_id": "abc123", "project_keys": ["PROJ", "ENG"]},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */6 * * *",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    # Add previous sync runs
    now = datetime.utcnow()
    previous_syncs = [
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=12),
            completed_at=now - timedelta(hours=12, minutes=-15),
            documents_added=50,
            documents_updated=10,
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6, minutes=-12),
            documents_added=8,
            documents_updated=15,
        ),
    ]
    
    for sync_run in previous_syncs:
        db_session.add(sync_run)
    db_session.commit()
    
    return connector


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario2_manual_sync_now(
    mock_task, client, existing_connector, db_session: Session
):
    """
    US2 Scenario 2: Manual sync now
    
    Steps:
    1. View existing connector with sync history
    2. Trigger immediate manual sync
    3. Verify sync starts
    4. Monitor sync progress
    5. Verify sync completes with updated documents
    """
    # Mock Celery task
    mock_result = MagicMock()
    mock_result.id = "manual-sync-task"
    mock_task.delay.return_value = mock_result
    
    connector_id = existing_connector.id
    
    # Step 1: View existing connector
    get_response = client.get(f"/v1/connectors/{connector_id}")
    
    assert get_response.status_code == 200
    data = get_response.json()
    
    assert data["id"] == connector_id
    assert data["connector_type"] == "jira"
    assert data["is_active"] is True
    assert len(data["recent_sync_runs"]) == 2
    
    # All previous syncs completed
    assert all(run["status"] == "completed" for run in data["recent_sync_runs"])
    
    # Step 2: Check sync history before manual sync
    history_before = client.get(f"/v1/connectors/{connector_id}/sync-runs")
    assert history_before.status_code == 200
    assert history_before.json()["total"] == 2
    
    # Step 3: Trigger immediate manual sync
    # Create sync run that would be created by task
    new_sync_run = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(new_sync_run)
    db_session.commit()
    db_session.refresh(new_sync_run)
    
    sync_response = client.post(f"/v1/connectors/{connector_id}/sync")
    
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    
    assert sync_data["status"] == "queued"
    assert sync_data["sync_run_id"] > 0
    assert "task_id" in sync_data["message"]
    
    # Verify Celery task was triggered
    mock_task.delay.assert_called_once_with(connector_id)
    
    # Step 4: Check sync is running
    history_running = client.get(f"/v1/connectors/{connector_id}/sync-runs")
    assert history_running.status_code == 200
    
    running_data = history_running.json()
    assert running_data["total"] == 3  # 2 previous + 1 new
    
    # Most recent should be running
    latest_run = running_data["sync_runs"][0]
    assert latest_run["status"] == "running"
    assert latest_run["completed_at"] is None
    
    # Step 5: Simulate sync completion with incremental changes
    new_sync_run.status = SyncStatus.COMPLETED.value
    new_sync_run.completed_at = datetime.utcnow()
    new_sync_run.documents_added = 12  # New documents
    new_sync_run.documents_updated = 25  # Updated documents
    new_sync_run.documents_deleted = 3  # Deleted documents
    db_session.commit()
    
    # Step 6: Verify sync completed
    history_completed = client.get(f"/v1/connectors/{connector_id}/sync-runs")
    assert history_completed.status_code == 200
    
    completed_data = history_completed.json()
    assert completed_data["total"] == 3
    
    latest_completed = completed_data["sync_runs"][0]
    assert latest_completed["status"] == "completed"
    assert latest_completed["completed_at"] is not None
    assert latest_completed["documents_added"] == 12
    assert latest_completed["documents_updated"] == 25
    assert latest_completed["documents_deleted"] == 3
    
    # Step 7: Verify connector shows updated sync status
    final_get = client.get(f"/v1/connectors/{connector_id}")
    final_data = final_get.json()
    
    assert final_data["last_sync_status"] == "completed"
    assert final_data["last_sync_at"] is not None
    assert len(final_data["recent_sync_runs"]) == 3
    
    print("✅ US2 Scenario 2: Manual sync now - PASSED")


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario2_sync_already_running(
    mock_task, client, existing_connector, db_session: Session
):
    """Test triggering sync when one is already running."""
    connector_id = existing_connector.id
    
    # Create running sync
    running_sync = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(running_sync)
    db_session.commit()
    
    # Try to trigger another sync without force
    response = client.post(f"/v1/connectors/{connector_id}/sync")
    
    assert response.status_code == 409  # Conflict
    data = response.json()
    assert "already in progress" in data["detail"].lower()
    
    # Should not have called task
    mock_task.delay.assert_not_called()


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario2_force_sync_while_running(
    mock_task, client, existing_connector, db_session: Session
):
    """Test force sync while another is running."""
    mock_result = MagicMock()
    mock_result.id = "force-task"
    mock_task.delay.return_value = mock_result
    
    connector_id = existing_connector.id
    
    # Create running sync
    running_sync = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(running_sync)
    db_session.commit()
    
    # Create new sync run for force trigger
    new_sync = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(new_sync)
    db_session.commit()
    
    # Trigger with force flag
    response = client.post(
        f"/v1/connectors/{connector_id}/sync",
        json={"force": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    
    # Should have called task despite running sync
    mock_task.delay.assert_called_once_with(connector_id)


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario2_inactive_connector(mock_task, client, db_session: Session):
    """Test manual sync on inactive connector."""
    # Create inactive connector
    connector = Connector(
        workspace_id=1,
        connector_type="slack",
        display_name="Inactive Slack",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=False,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    # Try to trigger sync
    response = client.post(f"/v1/connectors/{connector.id}/sync")
    
    assert response.status_code == 400
    data = response.json()
    assert "not active" in data["detail"].lower()
    
    # Should not have called task
    mock_task.delay.assert_not_called()


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario2_rapid_successive_syncs(
    mock_task, client, existing_connector, db_session: Session
):
    """Test multiple rapid sync triggers."""
    mock_result = MagicMock()
    mock_result.id = "rapid-task"
    mock_task.delay.return_value = mock_result
    
    connector_id = existing_connector.id
    
    # First sync - should succeed
    sync1 = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync1)
    db_session.commit()
    
    response1 = client.post(f"/v1/connectors/{connector_id}/sync")
    assert response1.status_code == 200
    
    # Second sync immediately - should conflict
    response2 = client.post(f"/v1/connectors/{connector_id}/sync")
    assert response2.status_code == 409
    
    # Complete first sync
    sync1.status = SyncStatus.COMPLETED.value
    sync1.completed_at = datetime.utcnow()
    db_session.commit()
    
    # Third sync - should succeed now
    sync3 = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync3)
    db_session.commit()
    
    response3 = client.post(f"/v1/connectors/{connector_id}/sync")
    assert response3.status_code == 200
    
    # Should have called task twice (first and third)
    assert mock_task.delay.call_count == 2
