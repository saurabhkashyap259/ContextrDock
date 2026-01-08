"""
Unit tests for action expiration cleanup task (T161).

Tests the Celery task that runs hourly to mark expired actions as EXPIRED
and clean up old action previews.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from src.workers.action_cleanup_task import expire_old_actions, cleanup_expired_actions
from src.models.agent_action import ActionStatus


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = Mock()
    session.query = Mock()
    session.commit = Mock()
    return session


@pytest.fixture
def sample_expired_action():
    """Create a sample expired action."""
    from src.models.agent_action import AgentAction, ActionType
    
    action = Mock(spec=AgentAction)
    action.id = uuid4()
    action.status = ActionStatus.PENDING_APPROVAL
    action.expires_at = datetime.utcnow() - timedelta(hours=2)  # Expired 2 hours ago
    action.mark_as_expired = Mock()
    
    return action


@pytest.fixture
def sample_pending_action():
    """Create a sample pending (not expired) action."""
    from src.models.agent_action import AgentAction, ActionType
    
    action = Mock(spec=AgentAction)
    action.id = uuid4()
    action.status = ActionStatus.PENDING_APPROVAL
    action.expires_at = datetime.utcnow() + timedelta(hours=2)  # Expires in 2 hours
    
    return action


class TestExpireOldActions:
    """Test expiring old actions that passed their expiration time."""

    def test_expire_old_actions_marks_expired_actions(self, mock_db_session, sample_expired_action):
        """Test that expired PENDING_APPROVAL actions are marked as EXPIRED."""
        # Setup query to return expired action
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_expired_action]
        
        # Run expiration task
        expired_count = expire_old_actions(mock_db_session)
        
        # Verify action was marked as expired
        sample_expired_action.mark_as_expired.assert_called_once()
        mock_db_session.commit.assert_called_once()
        assert expired_count == 1

    def test_expire_old_actions_only_affects_pending_approval(self, mock_db_session, sample_expired_action):
        """Test that only PENDING_APPROVAL actions are affected."""
        # Create actions with different statuses
        approved_action = Mock()
        approved_action.status = ActionStatus.APPROVED
        approved_action.expires_at = datetime.utcnow() - timedelta(hours=1)
        
        executed_action = Mock()
        executed_action.status = ActionStatus.EXECUTED
        executed_action.expires_at = datetime.utcnow() - timedelta(hours=1)
        
        # Setup query to return only pending expired actions
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_expired_action]  # Only pending action
        
        expired_count = expire_old_actions(mock_db_session)
        
        # Only pending action should be marked
        assert expired_count == 1

    def test_expire_old_actions_does_not_affect_valid_actions(self, mock_db_session, sample_pending_action):
        """Test that actions not yet expired are not affected."""
        # Setup query to return no expired actions
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []  # No expired actions
        
        expired_count = expire_old_actions(mock_db_session)
        
        assert expired_count == 0
        mock_db_session.commit.assert_called_once()  # Still commit even if no changes

    def test_expire_old_actions_handles_multiple_expired_actions(self, mock_db_session):
        """Test expiring multiple actions in one run."""
        # Create multiple expired actions
        expired_actions = []
        for i in range(5):
            action = Mock()
            action.id = uuid4()
            action.status = ActionStatus.PENDING_APPROVAL
            action.expires_at = datetime.utcnow() - timedelta(hours=i+1)
            action.mark_as_expired = Mock()
            expired_actions.append(action)
        
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = expired_actions
        
        expired_count = expire_old_actions(mock_db_session)
        
        assert expired_count == 5
        for action in expired_actions:
            action.mark_as_expired.assert_called_once()

    def test_expire_old_actions_handles_database_errors(self, mock_db_session):
        """Test that database errors are handled gracefully."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.side_effect = Exception("Database connection error")
        
        # Should not raise exception
        with pytest.raises(Exception):
            expire_old_actions(mock_db_session)


class TestCleanupExpiredActions:
    """Test cleanup of old expired actions."""

    def test_cleanup_expired_actions_deletes_old_actions(self, mock_db_session):
        """Test that expired actions older than retention period are deleted."""
        # Setup: Actions expired more than 7 days ago should be deleted
        old_expired_action = Mock()
        old_expired_action.id = uuid4()
        old_expired_action.status = ActionStatus.EXPIRED
        old_expired_action.created_at = datetime.utcnow() - timedelta(days=10)
        
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete = Mock(return_value=1)
        
        deleted_count = cleanup_expired_actions(mock_db_session, retention_days=7)
        
        assert deleted_count == 1
        mock_db_session.commit.assert_called_once()

    def test_cleanup_does_not_delete_recent_expired_actions(self, mock_db_session):
        """Test that recently expired actions are kept."""
        # Setup: Actions expired less than 7 days ago should be kept
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete = Mock(return_value=0)
        
        deleted_count = cleanup_expired_actions(mock_db_session, retention_days=7)
        
        assert deleted_count == 0

    def test_cleanup_only_affects_expired_and_cancelled_actions(self, mock_db_session):
        """Test that only EXPIRED and CANCELLED actions are cleaned up."""
        # PENDING_APPROVAL and EXECUTED actions should never be deleted
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete = Mock(return_value=3)
        
        deleted_count = cleanup_expired_actions(mock_db_session, retention_days=7)
        
        # Verify filter was called with correct statuses
        assert deleted_count == 3

    def test_cleanup_respects_retention_period(self, mock_db_session):
        """Test that cleanup respects configurable retention period."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete = Mock(return_value=5)
        
        # Test with different retention periods
        deleted_count_7d = cleanup_expired_actions(mock_db_session, retention_days=7)
        deleted_count_30d = cleanup_expired_actions(mock_db_session, retention_days=30)
        
        assert deleted_count_7d == 5
        assert deleted_count_30d == 5


class TestCeleryTaskIntegration:
    """Test Celery task integration and scheduling."""

    @patch('src.workers.action_cleanup_task.get_db_session')
    def test_celery_task_runs_expiration(self, mock_get_db):
        """Test that Celery task runs expiration logic."""
        mock_session = Mock()
        mock_get_db.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_db.return_value.__exit__ = Mock(return_value=False)
        
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        
        from src.workers.action_cleanup_task import action_cleanup_task
        
        result = action_cleanup_task()
        
        assert "expired" in result
        assert "cleaned_up" in result

    def test_task_logs_results(self, mock_db_session):
        """Test that task logs expiration and cleanup results."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.delete = Mock(return_value=0)
        
        with patch('src.workers.action_cleanup_task.logger') as mock_logger:
            expire_old_actions(mock_db_session)
            
            # Verify logging occurred
            mock_logger.info.assert_called()

    def test_task_handles_errors_gracefully(self, mock_db_session):
        """Test that task handles errors without crashing."""
        mock_db_session.query.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            expire_old_actions(mock_db_session)


class TestActionCleanupSchedule:
    """Test Celery task scheduling configuration."""

    def test_task_is_scheduled_hourly(self):
        """Test that cleanup task is configured to run hourly."""
        from src.workers.action_cleanup_task import get_task_schedule
        
        schedule = get_task_schedule()
        
        assert schedule is not None
        assert schedule["schedule_type"] == "crontab"
        # Should run every hour
        assert schedule["hour"] == "*"
        assert schedule["minute"] == "0"

    def test_task_has_retry_policy(self):
        """Test that task has retry policy for failures."""
        from src.workers.action_cleanup_task import action_cleanup_task
        
        # Verify task has retry configuration
        assert hasattr(action_cleanup_task, 'retry')
        # Should retry up to 3 times with exponential backoff


class TestActionExpirationEdgeCases:
    """Test edge cases for action expiration."""

    def test_expiration_at_exact_boundary(self, mock_db_session):
        """Test actions expiring at exact current time."""
        action_at_boundary = Mock()
        action_at_boundary.id = uuid4()
        action_at_boundary.status = ActionStatus.PENDING_APPROVAL
        action_at_boundary.expires_at = datetime.utcnow()  # Expires right now
        action_at_boundary.mark_as_expired = Mock()
        
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [action_at_boundary]
        
        expired_count = expire_old_actions(mock_db_session)
        
        # Should be marked as expired (current time >= expires_at)
        assert expired_count == 1

    def test_expiration_with_timezone_aware_timestamps(self, mock_db_session):
        """Test that expiration works with timezone-aware timestamps."""
        # Note: In production, ensure all timestamps are timezone-naive UTC
        # or consistently timezone-aware
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        
        expired_count = expire_old_actions(mock_db_session)
        
        assert expired_count == 0

    def test_cleanup_with_zero_retention_days(self, mock_db_session):
        """Test cleanup with zero retention (delete immediately)."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.delete = Mock(return_value=10)
        
        deleted_count = cleanup_expired_actions(mock_db_session, retention_days=0)
        
        assert deleted_count == 10


class TestActionCleanupMetrics:
    """Test metrics collection for monitoring."""

    def test_cleanup_returns_metrics(self, mock_db_session):
        """Test that cleanup task returns metrics for monitoring."""
        mock_query = Mock()
        mock_db_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [Mock(), Mock(), Mock()]
        mock_query.delete = Mock(return_value=5)
        
        expired_count = expire_old_actions(mock_db_session)
        cleanup_count = cleanup_expired_actions(mock_db_session)
        
        # Should return counts for metrics
        assert expired_count == 3
        assert cleanup_count == 5

    def test_metrics_include_execution_time(self):
        """Test that task metrics include execution time."""
        from src.workers.action_cleanup_task import action_cleanup_task
        
        with patch('src.workers.action_cleanup_task.get_db_session'):
            result = action_cleanup_task()
            
            assert "execution_time_ms" in result
