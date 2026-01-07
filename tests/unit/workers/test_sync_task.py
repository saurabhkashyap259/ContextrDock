"""Unit tests for sync task."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from src.workers.sync_task import run_connector_sync
from src.models.connector import Connector
from src.models.sync_run import SyncRun, SyncStatus
from src.models.workspace import Workspace


@pytest.fixture
def mock_workspace(db_session):
    """Create a mock workspace."""
    workspace = Workspace(
        name="Test Workspace",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def mock_connector(db_session, mock_workspace):
    """Create a mock connector."""
    connector = Connector(
        workspace_id=mock_workspace.id,
        connector_type="slack",
        display_name="Test Slack",
        config={"workspace_url": "https://test.slack.com"},
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(connector)
    db_session.commit()
    return connector


class TestSyncTask:
    """Test sync task functionality."""

    @patch("src.workers.sync_task.get_connector_class")
    @patch("src.workers.sync_task.ingest_document")
    def test_sync_task_success(
        self,
        mock_ingest_document,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test successful sync task execution."""
        # Setup mock connector instance
        mock_connector_instance = Mock()
        mock_connector_instance.sync.return_value = [
            {
                "source_id": "slack_msg_1",
                "source_type": "slack",
                "title": "Test Message",
                "content": "Test content",
                "metadata": {"channel": "general"},
                "acl": {"access_level": "public"},
                "source_url": "https://slack.com/archives/C123/p456",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]
        mock_get_connector_class.return_value = Mock(
            return_value=mock_connector_instance
        )

        # Setup mock ingest function
        mock_doc = Mock()
        mock_doc.document_chunks = []  # New document
        mock_ingest_document.return_value = mock_doc

        # Run sync task
        result = run_connector_sync(mock_connector.id)

        # Verify results
        assert result["status"] == "success"
        assert result["documents_processed"] == 1
        assert result["documents_added"] == 1

        # Verify connector was called
        mock_connector_instance.sync.assert_called_once()

        # Verify ingest was called
        mock_ingest_document.assert_called_once()

    @patch("src.workers.sync_task.get_connector_class")
    def test_sync_task_connector_error(
        self,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test sync task with connector error."""
        # Setup mock connector to raise error
        mock_connector_instance = Mock()
        mock_connector_instance.sync.side_effect = Exception("API Error")
        mock_get_connector_class.return_value = Mock(
            return_value=mock_connector_instance
        )

        # Run sync task - should handle error gracefully
        with pytest.raises(Exception) as exc_info:
            run_connector_sync(mock_connector.id)

        assert "API Error" in str(exc_info.value)

        # Verify sync run was created with error status
        sync_runs = db_session.query(SyncRun).filter_by(
            connector_id=mock_connector.id
        ).all()
        assert len(sync_runs) > 0
        assert sync_runs[-1].status == SyncStatus.FAILED

    @patch("src.workers.sync_task.get_connector_class")
    @patch("src.workers.sync_task.ingest_document")
    def test_sync_task_with_cursor_state(
        self,
        mock_ingest_document,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test sync task with existing cursor state for incremental sync."""
        # Create previous sync run with cursor state
        previous_run = SyncRun(
            connector_id=mock_connector.id,
            status=SyncStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            cursor_state={"last_updated": "2024-01-01T00:00:00Z"},
        )
        db_session.add(previous_run)
        db_session.commit()

        # Setup mock connector
        mock_connector_instance = Mock()
        mock_connector_instance.sync.return_value = []
        mock_get_connector_class.return_value = Mock(
            return_value=mock_connector_instance
        )

        # Run sync task
        result = run_connector_sync(mock_connector.id)

        # Verify cursor state was passed to connector
        mock_connector_instance.sync.assert_called_once()
        call_kwargs = mock_connector_instance.sync.call_args[1]
        assert "cursor_state" in call_kwargs
        assert call_kwargs["cursor_state"]["last_updated"] == "2024-01-01T00:00:00Z"

    @patch("src.workers.sync_task.get_connector_class")
    @patch("src.workers.sync_task.ingest_document")
    def test_sync_task_updates_documents(
        self,
        mock_ingest_document,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test sync task handles document updates."""
        # Setup mock connector with document that already exists
        mock_connector_instance = Mock()
        mock_connector_instance.sync.return_value = [
            {
                "source_id": "slack_msg_1",
                "source_type": "slack",
                "title": "Updated Message",
                "content": "Updated content",
                "metadata": {"channel": "general"},
                "acl": {"access_level": "public"},
                "source_url": "https://slack.com/archives/C123/p456",
                "timestamp": "2024-01-02T00:00:00Z",
            }
        ]
        mock_get_connector_class.return_value = Mock(
            return_value=mock_connector_instance
        )

        # Setup mock ingest - document has chunks (already existed)
        mock_doc = Mock()
        mock_doc.document_chunks = [Mock(), Mock(), Mock()]  # Existing document
        mock_ingest_document.return_value = mock_doc

        # Run sync task
        result = run_connector_sync(mock_connector.id)

        # Verify results
        assert result["status"] == "success"
        assert result["documents_updated"] == 1

    @patch("src.workers.sync_task.get_connector_class")
    def test_sync_task_inactive_connector(
        self,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test sync task skips inactive connectors."""
        # Deactivate connector
        mock_connector.is_active = False
        db_session.commit()

        # Run sync task
        result = run_connector_sync(mock_connector.id)

        # Verify connector was not called
        mock_get_connector_class.assert_not_called()

        # Verify result indicates skipped
        assert result["status"] == "skipped"
        assert "inactive" in result["message"].lower()

    def test_sync_task_nonexistent_connector(self, db_session):
        """Test sync task with non-existent connector ID."""
        # Run sync task with invalid ID
        with pytest.raises(Exception) as exc_info:
            run_connector_sync(999999)

        assert "not found" in str(exc_info.value).lower() or "does not exist" in str(exc_info.value).lower()

    @patch("src.workers.sync_task.get_connector_class")
    @patch("src.workers.sync_task.ingest_document")
    def test_sync_task_saves_cursor_state(
        self,
        mock_ingest_document,
        mock_get_connector_class,
        db_session,
        mock_connector,
    ):
        """Test sync task saves cursor state for next run."""
        # Setup mock connector
        mock_connector_instance = Mock()
        mock_connector_instance.sync.return_value = [
            {
                "source_id": "slack_msg_1",
                "source_type": "slack",
                "title": "Test Message",
                "content": "Test content",
                "metadata": {"channel": "general"},
                "acl": {"access_level": "public"},
                "source_url": "https://slack.com/archives/C123/p456",
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]
        # Mock connector returns cursor state
        mock_connector_instance.get_cursor_state.return_value = {
            "last_updated": "2024-01-01T00:00:00Z"
        }
        mock_get_connector_class.return_value = Mock(
            return_value=mock_connector_instance
        )

        # Setup mock ingest
        mock_doc = Mock()
        mock_doc.document_chunks = []
        mock_ingest_document.return_value = mock_doc

        # Run sync task
        result = run_connector_sync(mock_connector.id)

        # Verify sync run has cursor state
        sync_runs = db_session.query(SyncRun).filter_by(
            connector_id=mock_connector.id
        ).all()
        assert len(sync_runs) > 0
        last_run = sync_runs[-1]
        assert last_run.cursor_state is not None
