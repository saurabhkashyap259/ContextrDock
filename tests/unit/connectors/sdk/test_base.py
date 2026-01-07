"""Tests for ConnectorBase abstract class."""

import pytest
from abc import ABC
from datetime import datetime, timezone
from typing import Iterator, Dict, List, Any
from unittest.mock import Mock, patch

from src.connectors.sdk.base import ConnectorBase
from src.models.connector import Connector
from src.models.sync_run import SyncRun


class ConcreteConnector(ConnectorBase):
    """Concrete implementation for testing."""
    
    def sync(self) -> Iterator[Dict[str, Any]]:
        """Concrete implementation of sync method."""
        yield {
            "title": "Test Document",
            "content": "Test content",
            "source_id": "test-123",
            "source_url": "https://example.com/test-123",
            "metadata": {"author": "test@example.com"}
        }
    
    def fetch_page(self, cursor: str | None = None) -> tuple[List[Dict[str, Any]], str | None]:
        """Concrete implementation of fetch_page method."""
        if cursor is None:
            return ([{"id": "1", "data": "page1"}], "cursor_1")
        elif cursor == "cursor_1":
            return ([{"id": "2", "data": "page2"}], None)
        return ([], None)
    
    def extract_acl(self, document: Dict[str, Any]) -> List[str]:
        """Concrete implementation of extract_acl method."""
        return ["user@example.com"]


def test_connector_base_is_abstract():
    """Test that ConnectorBase cannot be instantiated directly."""
    # ConnectorBase should be an ABC
    assert issubclass(ConnectorBase, ABC)
    
    # Attempting to instantiate should raise TypeError
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        ConnectorBase(connector=Mock(), db_session=Mock())


def test_connector_base_requires_sync_method():
    """Test that subclasses must implement sync method."""
    class IncompleteConnector(ConnectorBase):
        def fetch_page(self, cursor=None):
            pass
        def extract_acl(self, document):
            pass
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteConnector(connector=Mock(), db_session=Mock())


def test_connector_base_requires_fetch_page_method():
    """Test that subclasses must implement fetch_page method."""
    class IncompleteConnector(ConnectorBase):
        def sync(self):
            pass
        def extract_acl(self, document):
            pass
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteConnector(connector=Mock(), db_session=Mock())


def test_connector_base_requires_extract_acl_method():
    """Test that subclasses must implement extract_acl method."""
    class IncompleteConnector(ConnectorBase):
        def sync(self):
            pass
        def fetch_page(self, cursor=None):
            pass
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteConnector(connector=Mock(), db_session=Mock())


def test_connector_base_initialization():
    """Test ConnectorBase initialization with connector and db_session."""
    mock_connector = Mock(spec=Connector)
    mock_connector.id = 1
    mock_connector.name = "Test Connector"
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    assert connector_instance.connector == mock_connector
    assert connector_instance.db_session == mock_db_session


def test_concrete_connector_sync():
    """Test concrete connector sync method returns document iterator."""
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    documents = list(connector_instance.sync())
    
    assert len(documents) == 1
    assert documents[0]["title"] == "Test Document"
    assert documents[0]["source_id"] == "test-123"


def test_concrete_connector_fetch_page():
    """Test concrete connector pagination."""
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    # First page
    page1, cursor1 = connector_instance.fetch_page(cursor=None)
    assert len(page1) == 1
    assert page1[0]["id"] == "1"
    assert cursor1 == "cursor_1"
    
    # Second page
    page2, cursor2 = connector_instance.fetch_page(cursor=cursor1)
    assert len(page2) == 1
    assert page2[0]["id"] == "2"
    assert cursor2 is None  # No more pages


def test_concrete_connector_extract_acl():
    """Test concrete connector ACL extraction."""
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    document = {"title": "Test Doc", "author": "user@example.com"}
    acl = connector_instance.extract_acl(document)
    
    assert len(acl) == 1
    assert "user@example.com" in acl


def test_connector_base_lifecycle_hooks():
    """Test that ConnectorBase supports lifecycle hooks."""
    # This test verifies that the base class design supports hooks
    # Actual hook implementations will be tested in integration tests
    
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    # Verify connector has access to connector and db_session for hooks
    assert hasattr(connector_instance, 'connector')
    assert hasattr(connector_instance, 'db_session')
    
    # These attributes enable subclasses to implement before_sync, after_sync, on_error hooks


def test_load_cursor_state():
    """Test loading cursor state from connector for incremental sync."""
    mock_connector = Mock(spec=Connector)
    mock_connector.cursor_state_json = {"page_token": "abc123", "last_ts": 1234567890}
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    cursor_state = connector_instance.load_cursor_state()
    
    assert cursor_state == {"page_token": "abc123", "last_ts": 1234567890}


def test_load_cursor_state_when_none():
    """Test loading cursor state when none exists (first sync)."""
    mock_connector = Mock(spec=Connector)
    mock_connector.cursor_state_json = None
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    cursor_state = connector_instance.load_cursor_state()
    
    assert cursor_state == {}


def test_save_cursor_state():
    """Test saving cursor state to connector for incremental sync."""
    mock_connector = Mock(spec=Connector)
    mock_connector.cursor_state_json = None
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    new_state = {"page_token": "xyz789", "last_ts": 1234567999}
    connector_instance.save_cursor_state(new_state)
    
    assert connector_instance.connector.cursor_state_json == new_state
    mock_db_session.commit.assert_called_once()


def test_create_sync_run():
    """Test creating a SyncRun record for tracking."""
    mock_connector = Mock(spec=Connector)
    mock_connector.id = 42
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    with patch('src.connectors.sdk.base.SyncRun') as mock_sync_run_class:
        mock_sync_run = Mock(spec=SyncRun)
        mock_sync_run_class.return_value = mock_sync_run
        
        sync_run = connector_instance.create_sync_run()
        
        # Verify SyncRun was created with correct connector_id and running status
        mock_sync_run_class.assert_called_once()
        call_kwargs = mock_sync_run_class.call_args[1]
        assert call_kwargs["connector_id"] == 42
        assert call_kwargs["status"] == "running"
        assert "started_at" in call_kwargs
        
        # Verify sync_run was added to session
        mock_db_session.add.assert_called_once_with(mock_sync_run)
        mock_db_session.commit.assert_called_once()


def test_complete_sync_run_success():
    """Test completing sync run with success status."""
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    mock_sync_run = Mock(spec=SyncRun)
    mock_sync_run.status = "running"
    
    connector_instance.complete_sync_run(
        sync_run=mock_sync_run,
        status="completed",
        documents_added=10,
        documents_updated=5,
        documents_deleted=2
    )
    
    assert mock_sync_run.status == "completed"
    assert mock_sync_run.documents_added == 10
    assert mock_sync_run.documents_updated == 5
    assert mock_sync_run.documents_deleted == 2
    assert mock_sync_run.completed_at is not None
    mock_db_session.commit.assert_called_once()


def test_complete_sync_run_failure():
    """Test completing sync run with failure status and error message."""
    mock_connector = Mock(spec=Connector)
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    mock_sync_run = Mock(spec=SyncRun)
    mock_sync_run.status = "running"
    
    connector_instance.complete_sync_run(
        sync_run=mock_sync_run,
        status="failed",
        error_message="API rate limit exceeded"
    )
    
    assert mock_sync_run.status == "failed"
    assert mock_sync_run.error_message == "API rate limit exceeded"
    assert mock_sync_run.completed_at is not None
    mock_db_session.commit.assert_called_once()


def test_update_last_synced_at():
    """Test updating connector's last_synced_at timestamp."""
    mock_connector = Mock(spec=Connector)
    mock_connector.last_synced_at = None
    mock_db_session = Mock()
    
    connector_instance = ConcreteConnector(
        connector=mock_connector,
        db_session=mock_db_session
    )
    
    connector_instance.update_last_synced_at()
    
    assert mock_connector.last_synced_at is not None
    assert isinstance(mock_connector.last_synced_at, datetime)
    mock_db_session.commit.assert_called_once()
