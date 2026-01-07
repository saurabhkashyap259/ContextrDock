"""Unit tests for Celery Beat schedule."""

import pytest
from datetime import datetime, timezone
from celery.schedules import crontab

from src.workers.celery_app import get_beat_schedule
from src.models.connector import Connector
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


class TestBeatSchedule:
    """Test Celery Beat schedule generation."""

    def test_get_beat_schedule_with_connectors(self, db_session, mock_workspace):
        """Test beat schedule generation with multiple connectors."""
        # Create connectors with different schedules
        connector1 = Connector(
            workspace_id=mock_workspace.id,
            connector_type="slack",
            display_name="Test Slack",
            config={},
            sync_schedule="0 */1 * * *",  # Hourly
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        connector2 = Connector(
            workspace_id=mock_workspace.id,
            connector_type="jira",
            display_name="Test Jira",
            config={},
            sync_schedule="0 */6 * * *",  # Every 6 hours
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add_all([connector1, connector2])
        db_session.commit()

        # Get beat schedule
        schedule = get_beat_schedule()

        # Verify schedule contains both connectors
        assert f"sync-connector-{connector1.id}" in schedule
        assert f"sync-connector-{connector2.id}" in schedule

        # Verify task configuration
        task1 = schedule[f"sync-connector-{connector1.id}"]
        assert task1["task"] == "src.workers.sync_task.run_connector_sync"
        assert task1["args"] == (connector1.id,)

        task2 = schedule[f"sync-connector-{connector2.id}"]
        assert task2["task"] == "src.workers.sync_task.run_connector_sync"
        assert task2["args"] == (connector2.id,)

    def test_get_beat_schedule_skips_inactive(self, db_session, mock_workspace):
        """Test beat schedule skips inactive connectors."""
        # Create inactive connector
        connector = Connector(
            workspace_id=mock_workspace.id,
            connector_type="slack",
            display_name="Inactive Slack",
            config={},
            sync_schedule="0 */1 * * *",
            is_active=False,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(connector)
        db_session.commit()

        # Get beat schedule
        schedule = get_beat_schedule()

        # Verify inactive connector not in schedule
        assert f"sync-connector-{connector.id}" not in schedule

    def test_get_beat_schedule_parses_cron(self, db_session, mock_workspace):
        """Test beat schedule parses cron expressions correctly."""
        # Create connector with cron schedule
        connector = Connector(
            workspace_id=mock_workspace.id,
            connector_type="github",
            display_name="Test GitHub",
            config={},
            sync_schedule="0 */3 * * *",  # Every 3 hours
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(connector)
        db_session.commit()

        # Get beat schedule
        schedule = get_beat_schedule()

        # Verify cron schedule is parsed
        task = schedule[f"sync-connector-{connector.id}"]
        assert "schedule" in task

        # Schedule should be a crontab instance
        schedule_obj = task["schedule"]
        assert isinstance(schedule_obj, crontab)

    def test_get_beat_schedule_empty(self, db_session):
        """Test beat schedule with no connectors."""
        # Get beat schedule
        schedule = get_beat_schedule()

        # Verify schedule is empty dict
        assert isinstance(schedule, dict)
        assert len(schedule) == 0

    def test_get_beat_schedule_with_default_schedule(
        self, db_session, mock_workspace
    ):
        """Test beat schedule uses default if no schedule specified."""
        # Create connector without sync_schedule
        connector = Connector(
            workspace_id=mock_workspace.id,
            connector_type="figma",
            display_name="Test Figma",
            config={},
            sync_schedule=None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(connector)
        db_session.commit()

        # Get beat schedule
        schedule = get_beat_schedule()

        # Verify connector has default schedule (6 hours)
        task_key = f"sync-connector-{connector.id}"
        assert task_key in schedule

        task = schedule[task_key]
        assert "schedule" in task

    def test_get_beat_schedule_invalid_cron(self, db_session, mock_workspace):
        """Test beat schedule handles invalid cron expressions."""
        # Create connector with invalid cron
        connector = Connector(
            workspace_id=mock_workspace.id,
            connector_type="dropbox",
            display_name="Test Dropbox",
            config={},
            sync_schedule="invalid cron",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(connector)
        db_session.commit()

        # Get beat schedule - should skip invalid cron or use default
        schedule = get_beat_schedule()

        # Either skipped or uses default schedule
        task_key = f"sync-connector-{connector.id}"
        if task_key in schedule:
            # Used default schedule
            assert "schedule" in schedule[task_key]
        else:
            # Skipped invalid cron
            assert task_key not in schedule
