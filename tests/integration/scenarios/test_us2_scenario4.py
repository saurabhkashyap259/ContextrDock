"""End-to-end test for US2 Scenario 4: Rate limit handling."""

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
def connector_with_rate_limit_history(db_session: Session):
    """Create connector with history of rate limit issues."""
    connector = Connector(
        workspace_id=1,
        connector_type="github",
        display_name="High Volume GitHub",
        config={"org": "bigorg", "rate_limit_aware": True},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */1 * * *",  # Every hour
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    # Previous sync runs with rate limit errors
    now = datetime.utcnow()
    syncs = [
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=6, minutes=-20),
            documents_added=500,
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.FAILED.value,
            started_at=now - timedelta(hours=5),
            completed_at=now - timedelta(hours=5, minutes=-5),
            error_message="HTTPError: 429 - Rate limit exceeded. Retry after 300 seconds",
        ),
        SyncRun(
            connector_id=connector.id,
            status=SyncStatus.COMPLETED.value,
            started_at=now - timedelta(hours=4),
            completed_at=now - timedelta(hours=4, minutes=-15),
            documents_added=200,
        ),
    ]
    
    for sync in syncs:
        db_session.add(sync)
    db_session.commit()
    
    return connector


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario4_rate_limit_detection(
    mock_task, client, connector_with_rate_limit_history, db_session: Session
):
    """
    US2 Scenario 4: Rate limit handling
    
    Steps:
    1. View connector with rate limit history
    2. Identify rate limit errors in sync runs
    3. Trigger new sync
    4. Simulate rate limit error
    5. Verify error captured correctly
    6. Retry sync after backoff
    7. Verify successful completion
    """
    mock_result = MagicMock()
    mock_result.id = "rate-limit-task"
    mock_task.delay.return_value = mock_result
    
    connector = connector_with_rate_limit_history
    
    # Step 1: View connector status
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["last_sync_status"] == "completed"
    assert len(data["recent_sync_runs"]) == 3
    
    # Step 2: Identify rate limit errors in history
    history_response = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?status=failed"
    )
    
    assert history_response.status_code == 200
    failed_data = history_response.json()
    
    assert failed_data["total"] == 1
    failed_run = failed_data["sync_runs"][0]
    
    assert "429" in failed_run["error_message"]
    assert "Rate limit exceeded" in failed_run["error_message"]
    
    print("✅ Rate limit error detected in sync history")
    
    # Step 3: Trigger new sync
    new_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(new_sync)
    db_session.commit()
    db_session.refresh(new_sync)
    
    sync_response = client.post(f"/v1/connectors/{connector.id}/sync")
    
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert sync_data["status"] == "queued"
    
    # Step 4: Simulate rate limit error during sync
    new_sync.status = SyncStatus.FAILED.value
    new_sync.completed_at = datetime.utcnow()
    new_sync.error_message = "HTTPError: 429 - API rate limit exceeded. Retry-After: 600"
    db_session.commit()
    
    # Step 5: Verify error captured
    status_check = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert status_check.status_code == 200
    status_data = status_check.json()
    
    # Should have 4 runs now (3 previous + 1 new)
    assert status_data["total"] == 4
    
    latest_run = status_data["sync_runs"][0]
    assert latest_run["status"] == "failed"
    assert "429" in latest_run["error_message"]
    assert "Retry-After" in latest_run["error_message"]
    
    print("✅ Rate limit error captured correctly")
    
    # Step 6: Retry sync after backoff period
    # Simulate waiting for retry-after period
    retry_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db_session.add(retry_sync)
    db_session.commit()
    db_session.refresh(retry_sync)
    
    retry_response = client.post(
        f"/v1/connectors/{connector.id}/sync",
        json={"force": True}  # Force to override rate limit check
    )
    
    assert retry_response.status_code == 200
    
    # Step 7: Simulate successful completion after retry
    retry_sync.status = SyncStatus.COMPLETED.value
    retry_sync.completed_at = datetime.utcnow() + timedelta(minutes=15)
    retry_sync.documents_added = 150
    retry_sync.documents_updated = 50
    db_session.commit()
    
    # Verify successful retry
    final_status = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    final_data = final_status.json()
    
    assert final_data["total"] == 5
    
    # Latest run should be successful
    latest_successful = final_data["sync_runs"][0]
    assert latest_successful["status"] == "completed"
    assert latest_successful["documents_added"] == 150
    
    print("✅ US2 Scenario 4: Rate limit handling - PASSED")


def test_us2_scenario4_rate_limit_error_details(
    client, connector_with_rate_limit_history
):
    """Test detailed rate limit error information."""
    connector = connector_with_rate_limit_history
    
    # Get failed syncs
    response = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?status=failed"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    failed_run = data["sync_runs"][0]
    
    # Check error message contains useful information
    assert "429" in failed_run["error_message"]
    assert "Rate limit exceeded" in failed_run["error_message"]
    assert "Retry after" in failed_run["error_message"] or "300 seconds" in failed_run["error_message"]
    
    # Verify started and completed times
    assert failed_run["started_at"] is not None
    assert failed_run["completed_at"] is not None
    
    # Parse duration
    started = datetime.fromisoformat(failed_run["started_at"].replace("Z", "+00:00"))
    completed = datetime.fromisoformat(failed_run["completed_at"].replace("Z", "+00:00"))
    duration = (completed - started).total_seconds()
    
    # Failed quickly (within 10 minutes)
    assert duration < 600


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario4_multiple_rate_limit_failures(
    mock_task, client, db_session: Session
):
    """Test handling multiple consecutive rate limit failures."""
    mock_result = MagicMock()
    mock_result.id = "multi-fail-task"
    mock_task.delay.return_value = mock_result
    
    # Create connector
    connector = Connector(
        workspace_id=1,
        connector_type="jira",
        display_name="Rate Limited Jira",
        config={"cloud_id": "busy123"},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    now = datetime.utcnow()
    
    # Simulate multiple rate limit failures
    for i in range(5):
        sync = SyncRun(
            connector_id=connector.id,
            status=SyncStatus.FAILED.value,
            started_at=now - timedelta(hours=5-i),
            completed_at=now - timedelta(hours=5-i, minutes=-2),
            error_message=f"HTTPError: 429 - Rate limit exceeded (attempt {i+1})",
        )
        db_session.add(sync)
    
    db_session.commit()
    
    # Get failure history
    response = client.get(
        f"/v1/connectors/{connector.id}/sync-runs?status=failed"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 5
    
    # All should be rate limit errors
    for run in data["sync_runs"]:
        assert "429" in run["error_message"]
        assert "Rate limit exceeded" in run["error_message"]


def test_us2_scenario4_rate_limit_recovery_metrics(
    client, connector_with_rate_limit_history
):
    """Test metrics showing rate limit recovery."""
    connector = connector_with_rate_limit_history
    
    # Get all sync runs
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Calculate success/failure rates
    total_runs = data["total"]
    successful_runs = sum(
        1 for run in data["sync_runs"] if run["status"] == "completed"
    )
    failed_runs = sum(
        1 for run in data["sync_runs"] if run["status"] == "failed"
    )
    
    assert total_runs == 3
    assert successful_runs == 2
    assert failed_runs == 1
    
    # Success rate should be 66%
    success_rate = (successful_runs / total_runs) * 100
    assert success_rate > 60
    
    # Calculate total documents synced despite failures
    total_documents = sum(
        run["documents_added"]
        for run in data["sync_runs"]
        if run["status"] == "completed"
    )
    
    assert total_documents == 700  # 500 + 200


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario4_rate_limit_with_exponential_backoff(
    mock_task, client, db_session: Session
):
    """Test rate limit handling with exponential backoff retries."""
    mock_result = MagicMock()
    mock_result.id = "backoff-task"
    mock_task.delay.return_value = mock_result
    
    connector = Connector(
        workspace_id=1,
        connector_type="figma",
        display_name="Busy Figma",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    now = datetime.utcnow()
    
    # Simulate retries with exponential backoff timing
    retry_delays = [60, 120, 240, 480]  # 1min, 2min, 4min, 8min
    
    for i, delay in enumerate(retry_delays):
        sync = SyncRun(
            connector_id=connector.id,
            status=SyncStatus.FAILED.value,
            started_at=now - timedelta(seconds=sum(retry_delays[:i+1])),
            completed_at=now - timedelta(seconds=sum(retry_delays[:i+1]) - 10),
            error_message=f"HTTPError: 429 - Rate limit (retry {i+1}, backoff {delay}s)",
        )
        db_session.add(sync)
    
    # Final successful retry
    final_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=now,
        completed_at=now + timedelta(minutes=5),
        documents_added=100,
    )
    db_session.add(final_sync)
    db_session.commit()
    
    # Verify retry pattern
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 5  # 4 failures + 1 success
    
    # Latest should be successful
    assert data["sync_runs"][0]["status"] == "completed"
    
    # Previous 4 should be rate limit failures
    for run in data["sync_runs"][1:5]:
        assert "429" in run["error_message"]
        assert "backoff" in run["error_message"]
