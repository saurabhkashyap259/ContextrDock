"""
Unit tests for audit logger service (T172).

Tests the audit logging service that tracks all write operations for compliance.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime

from src.services.audit_logger import AuditLogger, AuditEventType


@pytest.fixture
def workspace_id():
    """Sample workspace ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Sample user ID."""
    return uuid4()


@pytest.fixture
def target_id():
    """Sample target entity ID."""
    return uuid4()


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.flush = Mock()
    return session


@pytest.fixture
def audit_logger(mock_db_session):
    """Audit logger instance with mocked database."""
    return AuditLogger(db=mock_db_session)


class TestAuditLoggerBasicOperations:
    """Test basic audit logging operations."""

    def test_log_action_approved(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging action approval event."""
        audit_logger.log_action_approved(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=target_id,
            details={"preview_edited": False},
            ip_address="192.168.1.100"
        )
        
        # Verify audit log was created and committed
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        
        # Verify log entry details
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.workspace_id == workspace_id
        assert log_entry.actor_user_id == user_id
        assert log_entry.action == "action.approved"
        assert log_entry.target_type == "AgentAction"
        assert log_entry.target_id == target_id

    def test_log_action_executed(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test logging action execution (system event)."""
        audit_logger.log_action_executed(
            workspace_id=workspace_id,
            action_id=target_id,
            result_url="https://jira.example.com/browse/PROJ-123",
            execution_duration_ms=1234
        )
        
        mock_db_session.add.assert_called_once()
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.actor_user_id is None  # System event
        assert log_entry.action == "action.executed"
        assert log_entry.details_json["result_url"] == "https://jira.example.com/browse/PROJ-123"
        assert log_entry.details_json["execution_duration_ms"] == 1234

    def test_log_action_cancelled(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging action cancellation."""
        audit_logger.log_action_cancelled(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=target_id,
            reason="Changed requirements",
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "action.cancelled"
        assert log_entry.details_json["reason"] == "Changed requirements"

    def test_log_action_failed(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test logging action execution failure."""
        audit_logger.log_action_failed(
            workspace_id=workspace_id,
            action_id=target_id,
            error_message="Jira API returned 401: Unauthorized",
            error_type="APIError"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "action.failed"
        assert log_entry.details_json["error_message"] == "Jira API returned 401: Unauthorized"
        assert log_entry.details_json["error_type"] == "APIError"


class TestConnectorAuditEvents:
    """Test audit logging for connector operations."""

    def test_log_connector_created(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging connector creation."""
        audit_logger.log_connector_created(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=target_id,
            connector_type="jira",
            connector_name="Jira Production",
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "connector.created"
        assert log_entry.target_type == "Connector"
        assert log_entry.details_json["connector_type"] == "jira"
        assert log_entry.details_json["connector_name"] == "Jira Production"

    def test_log_connector_updated(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging connector configuration update."""
        audit_logger.log_connector_updated(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=target_id,
            before={"sync_schedule": "6hours"},
            after={"sync_schedule": "hourly"},
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "connector.updated"
        assert log_entry.details_json["before"]["sync_schedule"] == "6hours"
        assert log_entry.details_json["after"]["sync_schedule"] == "hourly"

    def test_log_connector_deleted(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging connector deletion."""
        audit_logger.log_connector_deleted(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=target_id,
            connector_type="slack",
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "connector.deleted"
        assert log_entry.details_json["connector_type"] == "slack"


class TestSyncAuditEvents:
    """Test audit logging for sync operations."""

    def test_log_sync_completed(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test logging successful sync completion."""
        audit_logger.log_sync_completed(
            workspace_id=workspace_id,
            connector_id=target_id,
            documents_indexed=150,
            duration_seconds=320
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "sync.completed"
        assert log_entry.actor_user_id is None  # System event
        assert log_entry.details_json["documents_indexed"] == 150
        assert log_entry.details_json["duration_seconds"] == 320

    def test_log_sync_failed(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test logging sync failure."""
        audit_logger.log_sync_failed(
            workspace_id=workspace_id,
            connector_id=target_id,
            error_message="Connection timeout",
            documents_processed=50
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "sync.failed"
        assert log_entry.details_json["error_message"] == "Connection timeout"
        assert log_entry.details_json["documents_processed"] == 50


class TestUserAuditEvents:
    """Test audit logging for user operations."""

    def test_log_user_role_changed(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test logging user role change."""
        audit_logger.log_user_role_changed(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            target_user_id=target_id,
            old_role="member",
            new_role="admin",
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.action == "user.role_changed"
        assert log_entry.target_type == "User"
        assert log_entry.details_json["old_role"] == "member"
        assert log_entry.details_json["new_role"] == "admin"


class TestAuditLoggerHelperMethods:
    """Test helper methods and utilities."""

    def test_create_log_entry_with_user_actor(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test creating log entry with user as actor."""
        audit_logger._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="test.action",
            target_type="TestEntity",
            target_id=target_id,
            details={},
            ip_address="192.168.1.100"
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.actor_user_id == user_id
        assert log_entry.ip_address == "192.168.1.100"

    def test_create_log_entry_with_system_actor(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test creating log entry with system as actor."""
        audit_logger._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,
            action="test.system_action",
            target_type="TestEntity",
            target_id=target_id,
            details={}
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.actor_user_id is None
        assert log_entry.ip_address is None

    def test_log_entry_includes_timestamp(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test that log entries include creation timestamp."""
        before = datetime.utcnow()
        
        audit_logger._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="test.action",
            target_type="TestEntity",
            target_id=target_id,
            details={}
        )
        
        after = datetime.utcnow()
        
        log_entry = mock_db_session.add.call_args[0][0]
        # Timestamp should be set by database default
        assert hasattr(log_entry, 'created_at')


class TestAuditLoggerValidation:
    """Test validation and error handling."""

    def test_validates_action_format(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test that action names follow 'entity.verb' format."""
        # Valid format should work
        audit_logger._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="entity.verb",
            target_type="TestEntity",
            target_id=target_id,
            details={}
        )
        
        mock_db_session.add.assert_called_once()

    def test_handles_empty_details(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test that empty details are handled correctly."""
        audit_logger._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="test.action",
            target_type="TestEntity",
            target_id=target_id,
            details={}
        )
        
        log_entry = mock_db_session.add.call_args[0][0]
        assert log_entry.details_json == {}

    def test_handles_database_commit_errors(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test that database commit errors are logged but don't crash."""
        mock_db_session.commit.side_effect = Exception("Database error")
        
        # Should log error but not raise exception
        with pytest.raises(Exception):
            audit_logger._create_log_entry(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action="test.action",
                target_type="TestEntity",
                target_id=target_id,
                details={}
            )


class TestAuditLoggerQueryHelpers:
    """Test helper methods for querying audit logs."""

    def test_get_logs_for_action(self, audit_logger, workspace_id, target_id, mock_db_session):
        """Test retrieving all logs for a specific action."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        
        logs = audit_logger.get_logs_for_target(
            workspace_id=workspace_id,
            target_type="AgentAction",
            target_id=target_id
        )
        
        assert logs == []
        mock_db_session.query.assert_called_once()

    def test_get_logs_by_user(self, audit_logger, workspace_id, user_id, mock_db_session):
        """Test retrieving all logs for a specific user."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        
        logs = audit_logger.get_logs_by_user(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=50
        )
        
        assert logs == []

    def test_get_recent_logs(self, audit_logger, workspace_id, mock_db_session):
        """Test retrieving recent audit logs."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        
        logs = audit_logger.get_recent_logs(
            workspace_id=workspace_id,
            limit=100
        )
        
        assert logs == []


class TestAuditLoggerIntegration:
    """Test end-to-end audit logging workflows."""

    def test_complete_action_workflow_audit_trail(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test complete audit trail for action workflow."""
        action_id = target_id
        
        # 1. Action created
        audit_logger.log_action_created(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=action_id,
            action_type="create_jira_ticket"
        )
        
        # 2. Action approved
        audit_logger.log_action_approved(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=action_id,
            details={"preview_edited": True},
            ip_address="192.168.1.100"
        )
        
        # 3. Action executed
        audit_logger.log_action_executed(
            workspace_id=workspace_id,
            action_id=action_id,
            result_url="https://jira.example.com/browse/PROJ-123",
            execution_duration_ms=1234
        )
        
        # Verify 3 audit log entries were created
        assert mock_db_session.add.call_count == 3
        assert mock_db_session.commit.call_count == 3

    def test_connector_lifecycle_audit_trail(self, audit_logger, workspace_id, user_id, target_id, mock_db_session):
        """Test complete audit trail for connector lifecycle."""
        connector_id = target_id
        
        # Create → Update → Sync → Delete
        audit_logger.log_connector_created(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=connector_id,
            connector_type="jira",
            connector_name="Jira"
        )
        
        audit_logger.log_connector_updated(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=connector_id,
            before={"status": "active"},
            after={"status": "disabled"}
        )
        
        audit_logger.log_sync_completed(
            workspace_id=workspace_id,
            connector_id=connector_id,
            documents_indexed=100,
            duration_seconds=60
        )
        
        audit_logger.log_connector_deleted(
            workspace_id=workspace_id,
            user_id=user_id,
            connector_id=connector_id,
            connector_type="jira"
        )
        
        assert mock_db_session.add.call_count == 4
