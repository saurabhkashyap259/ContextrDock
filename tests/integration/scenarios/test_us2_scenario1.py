"""End-to-end test for US2 Scenario 1: Add connector, validate, sync."""

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


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario1_add_connector_validate_sync(
    mock_task, client, db_session: Session
):
    """
    US2 Scenario 1: Add connector, validate, sync
    
    Steps:
    1. Create a new Slack connector via API
    2. Validate connector exists and has correct config
    3. Trigger manual sync
    4. Verify sync run created
    5. Check sync completes successfully
    """
    # Mock Celery task
    mock_result = MagicMock()
    mock_result.id = "scenario1-task"
    mock_task.delay.return_value = mock_result
    
    # Step 1: Create connector
    create_payload = {
        "connector_type": "slack",
        "display_name": "Engineering Team Slack",
        "config": {
            "team_id": "T123ABC",
            "channels": ["engineering", "general", "announcements"]
        },
        "credentials": {
            "access_token": "xoxb-test-token-12345",
            "token_type": "bearer",
            "scope": "channels:read,channels:history,users:read"
        },
        "sync_schedule": "0 */3 * * *",  # Every 3 hours
        "is_active": True
    }
    
    create_response = client.post("/v1/connectors", json=create_payload)
    
    assert create_response.status_code == 201
    connector_data = create_response.json()
    
    assert connector_data["connector_type"] == "slack"
    assert connector_data["display_name"] == "Engineering Team Slack"
    assert connector_data["is_active"] is True
    
    connector_id = connector_data["id"]
    
    # Step 2: Validate connector exists in database
    connector = db_session.query(Connector).filter_by(id=connector_id).first()
    
    assert connector is not None
    assert connector.workspace_id == 1
    assert connector.connector_type == "slack"
    assert connector.config["team_id"] == "T123ABC"
    assert len(connector.config["channels"]) == 3
    assert connector.credentials_encrypted is not None
    assert connector.sync_schedule == "0 */3 * * *"
    
    # Step 3: Get connector details via API
    get_response = client.get(f"/v1/connectors/{connector_id}")
    
    assert get_response.status_code == 200
    detail_data = get_response.json()
    
    assert detail_data["id"] == connector_id
    assert detail_data["display_name"] == "Engineering Team Slack"
    assert "credentials" not in detail_data  # Should not expose credentials
    assert "recent_sync_runs" in detail_data
    assert len(detail_data["recent_sync_runs"]) == 0  # No syncs yet
    
    # Step 4: Trigger manual sync
    # Create a sync run that would be created by the task
    sync_run = SyncRun(
        connector_id=connector_id,
        status=SyncStatus.RUNNING.value,
    )
    db_session.add(sync_run)
    db_session.commit()
    db_session.refresh(sync_run)
    
    sync_response = client.post(f"/v1/connectors/{connector_id}/sync")
    
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    
    assert sync_data["status"] == "queued"
    assert "sync_run_id" in sync_data
    assert sync_data["sync_run_id"] > 0
    
    # Verify Celery task was called
    mock_task.delay.assert_called_once_with(connector_id)
    
    # Step 5: Simulate sync completion
    sync_run.status = SyncStatus.COMPLETED.value
    sync_run.documents_added = 25
    sync_run.documents_updated = 3
    sync_run.documents_deleted = 0
    db_session.commit()
    
    # Step 6: Check sync history
    history_response = client.get(f"/v1/connectors/{connector_id}/sync-runs")
    
    assert history_response.status_code == 200
    history_data = history_response.json()
    
    assert history_data["total"] == 1
    assert len(history_data["sync_runs"]) == 1
    
    sync_run_data = history_data["sync_runs"][0]
    assert sync_run_data["status"] == "completed"
    assert sync_run_data["documents_added"] == 25
    assert sync_run_data["documents_updated"] == 3
    
    # Step 7: Verify connector shows last sync info
    final_get_response = client.get(f"/v1/connectors/{connector_id}")
    final_data = final_get_response.json()
    
    assert len(final_data["recent_sync_runs"]) == 1
    assert final_data["last_sync_status"] == "completed"
    assert final_data["last_sync_at"] is not None
    
    print("✅ US2 Scenario 1: Add connector, validate, sync - PASSED")


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario1_validation_errors(client):
    """Test validation errors when creating connector."""
    # Invalid connector type
    invalid_payload = {
        "connector_type": "invalid_type",
        "display_name": "Invalid Connector",
        "config": {},
        "credentials": {
            "access_token": "test"
        }
    }
    
    response = client.post("/v1/connectors", json=invalid_payload)
    assert response.status_code == 422
    
    # Invalid cron schedule
    invalid_cron_payload = {
        "connector_type": "slack",
        "display_name": "Bad Cron",
        "config": {},
        "credentials": {
            "access_token": "test"
        },
        "sync_schedule": "not a cron"
    }
    
    response = client.post("/v1/connectors", json=invalid_cron_payload)
    assert response.status_code == 422


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario1_multiple_connectors(mock_task, client, db_session: Session):
    """Test creating and syncing multiple connectors."""
    mock_result = MagicMock()
    mock_result.id = "multi-task"
    mock_task.delay.return_value = mock_result
    
    connector_types = ["slack", "jira", "github"]
    connector_ids = []
    
    for connector_type in connector_types:
        payload = {
            "connector_type": connector_type,
            "display_name": f"Test {connector_type}",
            "config": {"test": "config"},
            "credentials": {
                "access_token": f"token-{connector_type}"
            }
        }
        
        response = client.post("/v1/connectors", json=payload)
        assert response.status_code == 201
        
        data = response.json()
        connector_ids.append(data["id"])
    
    # List all connectors
    list_response = client.get("/v1/connectors")
    assert list_response.status_code == 200
    
    list_data = list_response.json()
    assert list_data["total"] == 3
    
    # Trigger sync on each
    for connector_id in connector_ids:
        # Create sync run
        sync_run = SyncRun(
            connector_id=connector_id,
            status=SyncStatus.RUNNING.value,
        )
        db_session.add(sync_run)
        db_session.commit()
        
        response = client.post(f"/v1/connectors/{connector_id}/sync")
        assert response.status_code == 200
    
    assert mock_task.delay.call_count == 3
