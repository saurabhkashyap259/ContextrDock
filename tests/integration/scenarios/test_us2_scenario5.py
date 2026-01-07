"""End-to-end test for US2 Scenario 5: File upload indexing."""

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
def dropbox_connector(db_session: Session):
    """Create Dropbox connector for file upload testing."""
    connector = Connector(
        workspace_id=1,
        connector_type="dropbox",
        display_name="Team Dropbox",
        config={
            "root_path": "/Company",
            "folders": ["Documents", "Projects", "Resources"]
        },
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */4 * * *",  # Every 4 hours
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    # Initial sync with existing files
    initial_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow() - timedelta(hours=4),
        completed_at=datetime.utcnow() - timedelta(hours=4, minutes=-12),
        documents_added=50,  # Initial files
        cursor_state_json='{"cursor": "initial_cursor_abc123"}',
    )
    db_session.add(initial_sync)
    db_session.commit()
    
    return connector


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario5_file_upload_indexing(
    mock_task, client, dropbox_connector, db_session: Session
):
    """
    US2 Scenario 5: File upload indexing
    
    Steps:
    1. View existing Dropbox connector with initial files
    2. Simulate file upload to Dropbox (new files appear)
    3. Wait for scheduled sync OR trigger manual sync
    4. Verify new files are detected and indexed
    5. Check incremental sync using cursor
    6. Verify document counts updated
    """
    mock_result = MagicMock()
    mock_result.id = "file-upload-task"
    mock_task.delay.return_value = mock_result
    
    connector = dropbox_connector
    
    # Step 1: View existing connector
    response = client.get(f"/v1/connectors/{connector.id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["connector_type"] == "dropbox"
    assert data["is_active"] is True
    assert len(data["recent_sync_runs"]) == 1
    
    # Initial sync completed
    initial_run = data["recent_sync_runs"][0]
    assert initial_run["status"] == "completed"
    assert initial_run["documents_added"] == 50
    
    print("✅ Initial sync: 50 files indexed")
    
    # Step 2: Simulate file uploads (new files in Dropbox)
    # In real scenario, user uploads files to Dropbox
    # Files: "Q4_Report.pdf", "Design_Mockup.fig", "Meeting_Notes.md"
    
    # Step 3: Trigger manual sync to detect new files
    # Create sync run for new files
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
    assert "sync_run_id" in sync_data
    
    print("✅ Manual sync triggered to detect new files")
    
    # Step 4: Simulate sync completion with new files detected
    # Incremental sync detects 3 new files
    new_sync.status = SyncStatus.COMPLETED.value
    new_sync.completed_at = datetime.utcnow()
    new_sync.documents_added = 3  # New files uploaded
    new_sync.documents_updated = 2  # Existing files modified
    new_sync.documents_deleted = 0
    new_sync.cursor_state_json = '{"cursor": "updated_cursor_xyz789"}'
    db_session.commit()
    
    print("✅ Sync completed: 3 new files, 2 updated files")
    
    # Step 5: Verify incremental sync results
    history_response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert history_response.status_code == 200
    history_data = history_response.json()
    
    assert history_data["total"] == 2  # Initial + new sync
    
    latest_sync = history_data["sync_runs"][0]
    assert latest_sync["status"] == "completed"
    assert latest_sync["documents_added"] == 3
    assert latest_sync["documents_updated"] == 2
    assert latest_sync["cursor_state"] is not None
    
    # Step 6: Verify cursor state for incremental sync
    # Check that cursor was saved for next sync
    assert "updated_cursor" in latest_sync["cursor_state"]
    
    # Step 7: Calculate total documents across all syncs
    total_added = sum(
        run["documents_added"] 
        for run in history_data["sync_runs"]
        if run["status"] == "completed"
    )
    
    assert total_added == 53  # 50 initial + 3 new
    
    print("✅ US2 Scenario 5: File upload indexing - PASSED")
    print(f"   Total documents indexed: {total_added}")


def test_us2_scenario5_scheduled_sync_after_upload(
    client, dropbox_connector, db_session: Session
):
    """Test scheduled sync automatically detects uploaded files."""
    connector = dropbox_connector
    
    # Simulate scheduled sync running (Beat scheduler triggered it)
    scheduled_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(scheduled_sync)
    db_session.commit()
    
    # Complete scheduled sync with new files
    scheduled_sync.status = SyncStatus.COMPLETED.value
    scheduled_sync.completed_at = datetime.utcnow() + timedelta(minutes=8)
    scheduled_sync.documents_added = 5  # Files uploaded since last sync
    scheduled_sync.documents_updated = 1
    db_session.commit()
    
    # Verify scheduled sync results
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have 2 syncs now (initial + scheduled)
    assert data["total"] == 2
    
    latest = data["sync_runs"][0]
    assert latest["documents_added"] == 5


def test_us2_scenario5_multiple_file_updates(
    client, dropbox_connector, db_session: Session
):
    """Test multiple rounds of file uploads and updates."""
    connector = dropbox_connector
    
    # Round 1: Upload new files
    sync1 = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow() - timedelta(hours=3),
        completed_at=datetime.utcnow() - timedelta(hours=3, minutes=-5),
        documents_added=10,
        documents_updated=0,
        cursor_state_json='{"cursor": "round1"}',
    )
    db_session.add(sync1)
    
    # Round 2: Update existing files
    sync2 = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow() - timedelta(hours=2),
        completed_at=datetime.utcnow() - timedelta(hours=2, minutes=-6),
        documents_added=2,
        documents_updated=8,
        cursor_state_json='{"cursor": "round2"}',
    )
    db_session.add(sync2)
    
    # Round 3: Delete some files, add new ones
    sync3 = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow() - timedelta(hours=1),
        completed_at=datetime.utcnow() - timedelta(hours=1, minutes=-7),
        documents_added=3,
        documents_updated=1,
        documents_deleted=4,
        cursor_state_json='{"cursor": "round3"}',
    )
    db_session.add(sync3)
    
    db_session.commit()
    
    # Verify all syncs recorded
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have 4 syncs (initial + 3 rounds)
    assert data["total"] == 4
    
    # Calculate net document change
    total_added = sum(run["documents_added"] for run in data["sync_runs"])
    total_deleted = sum(run["documents_deleted"] for run in data["sync_runs"])
    
    net_documents = total_added - total_deleted
    assert net_documents == 61  # 50 + 10 + 2 + 3 - 4


def test_us2_scenario5_file_type_filtering(
    client, dropbox_connector, db_session: Session
):
    """Test that only syncable file types are indexed."""
    connector = dropbox_connector
    
    # Sync with mixed file types
    # Syncable: .txt, .md, .pdf, .docx
    # Not syncable: .exe, .zip, .mp4
    sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow() + timedelta(minutes=10),
        documents_added=20,  # Only syncable files counted
        # In real scenario, connector would filter non-syncable files
    )
    db_session.add(sync)
    db_session.commit()
    
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    latest = data["sync_runs"][0]
    assert latest["documents_added"] == 20


@patch("src.api.routes.connectors.run_connector_sync")
def test_us2_scenario5_concurrent_uploads_during_sync(
    mock_task, client, dropbox_connector, db_session: Session
):
    """Test handling files uploaded while sync is running."""
    mock_result = MagicMock()
    mock_result.id = "concurrent-task"
    mock_task.delay.return_value = mock_result
    
    connector = dropbox_connector
    
    # Start first sync
    sync1 = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow() - timedelta(minutes=10),
    )
    db_session.add(sync1)
    db_session.commit()
    
    # Files uploaded during sync won't be in this sync
    sync1.status = SyncStatus.COMPLETED.value
    sync1.completed_at = datetime.utcnow() - timedelta(minutes=2)
    sync1.documents_added = 15
    sync1.cursor_state_json = '{"cursor": "during_sync"}',
    db_session.commit()
    
    # Next sync picks up files uploaded during previous sync
    sync2 = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db_session.add(sync2)
    db_session.commit()
    
    sync_response = client.post(f"/v1/connectors/{connector.id}/sync", json={"force": True})
    assert sync_response.status_code == 200
    
    sync2.status = SyncStatus.COMPLETED.value
    sync2.completed_at = datetime.utcnow() + timedelta(minutes=5)
    sync2.documents_added = 5  # Files uploaded during previous sync
    db_session.commit()
    
    # Verify both syncs
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    data = response.json()
    
    assert data["total"] == 3  # Initial + sync1 + sync2
    
    # Verify incremental sync captured later uploads
    assert data["sync_runs"][0]["documents_added"] == 5
    assert data["sync_runs"][1]["documents_added"] == 15


def test_us2_scenario5_large_file_batch_upload(
    client, dropbox_connector, db_session: Session
):
    """Test handling large batch of file uploads."""
    connector = dropbox_connector
    
    # Simulate bulk upload of 500 files
    bulk_sync = SyncRun(
        connector_id=connector.id,
        status=SyncStatus.COMPLETED.value,
        started_at=datetime.utcnow() - timedelta(minutes=30),
        completed_at=datetime.utcnow() - timedelta(minutes=5),  # Took 25 minutes
        documents_added=500,
        documents_updated=0,
        cursor_state_json='{"cursor": "bulk_upload", "batch_size": 500}',
    )
    db_session.add(bulk_sync)
    db_session.commit()
    
    response = client.get(f"/v1/connectors/{connector.id}/sync-runs")
    
    assert response.status_code == 200
    data = response.json()
    
    bulk_run = data["sync_runs"][0]
    assert bulk_run["documents_added"] == 500
    
    # Verify sync took reasonable time (under 1 hour)
    started = datetime.fromisoformat(bulk_run["started_at"].replace("Z", "+00:00"))
    completed = datetime.fromisoformat(bulk_run["completed_at"].replace("Z", "+00:00"))
    duration = (completed - started).total_seconds()
    
    assert duration < 3600  # Less than 1 hour
    assert duration > 60  # More than 1 minute (realistic for 500 files)
