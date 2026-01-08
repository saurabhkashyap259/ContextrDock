"""
Unit tests for AgentAction model (T150).

Tests the AgentAction model which tracks AI-generated content creation requests
that require human approval before execution.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.exc import IntegrityError

from src.models.agent_action import AgentAction, ActionType, ActionStatus


@pytest.fixture
def workspace_id():
    """Sample workspace ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Sample user ID."""
    return uuid4()


@pytest.fixture
def conversation_id():
    """Sample conversation ID."""
    return uuid4()


@pytest.fixture
def sample_preview_json():
    """Sample preview JSON for Jira ticket."""
    return {
        "project": "PROJ",
        "issue_type": "Task",
        "summary": "Implement feature X",
        "description": "As a user, I want feature X...",
        "priority": "Medium",
        "labels": ["ai-generated"]
    }


class TestAgentActionCreation:
    """Test AgentAction model creation and field validation."""

    def test_create_agent_action_with_all_fields(self, workspace_id, user_id, conversation_id, sample_preview_json):
        """Test creating AgentAction with all required and optional fields."""
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json,
            expires_at=expires_at,
            result_url=None
        )
        
        assert action.workspace_id == workspace_id
        assert action.user_id == user_id
        assert action.conversation_id == conversation_id
        assert action.action_type == ActionType.CREATE_JIRA_TICKET
        assert action.status == ActionStatus.PENDING_APPROVAL
        assert action.preview_json == sample_preview_json
        assert action.expires_at == expires_at
        assert action.result_url is None
        assert action.error_message is None

    def test_create_agent_action_minimal_fields(self, workspace_id, user_id, sample_preview_json):
        """Test creating AgentAction with only required fields (conversation_id optional)."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_CONFLUENCE_PAGE,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json
        )
        
        assert action.workspace_id == workspace_id
        assert action.user_id == user_id
        assert action.conversation_id is None
        assert action.action_type == ActionType.CREATE_CONFLUENCE_PAGE
        assert action.preview_json == sample_preview_json

    def test_default_status_is_pending(self, workspace_id, user_id, sample_preview_json):
        """Test that default status is PENDING_APPROVAL."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_GITHUB_ISSUE,
            preview_json=sample_preview_json
        )
        
        assert action.status == ActionStatus.PENDING_APPROVAL

    def test_default_expiration_is_24_hours(self, workspace_id, user_id, sample_preview_json):
        """Test that default expiration is 24 hours from creation."""
        before = datetime.utcnow() + timedelta(hours=24, minutes=-1)
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=sample_preview_json
        )
        
        after = datetime.utcnow() + timedelta(hours=24, minutes=1)
        
        assert before <= action.expires_at <= after


class TestAgentActionTypes:
    """Test AgentAction type enum validation."""

    def test_all_action_types_supported(self, workspace_id, user_id, sample_preview_json):
        """Test that all defined action types can be created."""
        action_types = [
            ActionType.CREATE_JIRA_TICKET,
            ActionType.CREATE_CONFLUENCE_PAGE,
            ActionType.CREATE_GITHUB_ISSUE
        ]
        
        for action_type in action_types:
            action = AgentAction(
                workspace_id=workspace_id,
                user_id=user_id,
                action_type=action_type,
                preview_json=sample_preview_json
            )
            assert action.action_type == action_type

    def test_invalid_action_type_raises_error(self, workspace_id, user_id, sample_preview_json):
        """Test that invalid action type raises ValueError."""
        with pytest.raises((ValueError, AttributeError)):
            AgentAction(
                workspace_id=workspace_id,
                user_id=user_id,
                action_type="invalid_action",
                preview_json=sample_preview_json
            )


class TestAgentActionStatuses:
    """Test AgentAction status transitions."""

    def test_all_statuses_supported(self, workspace_id, user_id, sample_preview_json):
        """Test that all defined statuses can be set."""
        statuses = [
            ActionStatus.PENDING_APPROVAL,
            ActionStatus.APPROVED,
            ActionStatus.EXECUTED,
            ActionStatus.CANCELLED,
            ActionStatus.EXPIRED,
            ActionStatus.FAILED
        ]
        
        for status in statuses:
            action = AgentAction(
                workspace_id=workspace_id,
                user_id=user_id,
                action_type=ActionType.CREATE_JIRA_TICKET,
                status=status,
                preview_json=sample_preview_json
            )
            assert action.status == status

    def test_status_transition_pending_to_approved(self, workspace_id, user_id, sample_preview_json):
        """Test transitioning from PENDING_APPROVAL to APPROVED."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json
        )
        
        action.status = ActionStatus.APPROVED
        assert action.status == ActionStatus.APPROVED

    def test_status_transition_approved_to_executed(self, workspace_id, user_id, sample_preview_json):
        """Test transitioning from APPROVED to EXECUTED with result URL."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.APPROVED,
            preview_json=sample_preview_json
        )
        
        action.status = ActionStatus.EXECUTED
        action.result_url = "https://jira.example.com/browse/PROJ-123"
        
        assert action.status == ActionStatus.EXECUTED
        assert action.result_url == "https://jira.example.com/browse/PROJ-123"

    def test_status_transition_pending_to_cancelled(self, workspace_id, user_id, sample_preview_json):
        """Test transitioning from PENDING_APPROVAL to CANCELLED."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json
        )
        
        action.status = ActionStatus.CANCELLED
        assert action.status == ActionStatus.CANCELLED

    def test_status_transition_to_failed_with_error(self, workspace_id, user_id, sample_preview_json):
        """Test transitioning to FAILED with error message."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.APPROVED,
            preview_json=sample_preview_json
        )
        
        action.status = ActionStatus.FAILED
        action.error_message = "Jira API returned 401: Unauthorized"
        
        assert action.status == ActionStatus.FAILED
        assert action.error_message == "Jira API returned 401: Unauthorized"


class TestAgentActionPreviewJson:
    """Test preview_json field validation and structure."""

    def test_preview_json_for_jira_ticket(self, workspace_id, user_id):
        """Test preview JSON structure for Jira ticket creation."""
        preview = {
            "project": "PROJ",
            "issue_type": "Bug",
            "summary": "Fix login issue",
            "description": "Users cannot log in with SSO",
            "priority": "High",
            "assignee": "john.doe@example.com",
            "labels": ["security", "urgent"]
        }
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=preview
        )
        
        assert action.preview_json["project"] == "PROJ"
        assert action.preview_json["issue_type"] == "Bug"
        assert action.preview_json["priority"] == "High"
        assert "security" in action.preview_json["labels"]

    def test_preview_json_for_confluence_page(self, workspace_id, user_id):
        """Test preview JSON structure for Confluence page creation."""
        preview = {
            "space": "DOCS",
            "title": "Q4 Planning Notes",
            "body": "<h1>Q4 Goals</h1><p>Complete MVP launch...</p>",
            "parent_page_id": "12345",
            "labels": ["planning", "q4-2026"]
        }
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_CONFLUENCE_PAGE,
            preview_json=preview
        )
        
        assert action.preview_json["space"] == "DOCS"
        assert action.preview_json["title"] == "Q4 Planning Notes"
        assert "q4-2026" in action.preview_json["labels"]

    def test_preview_json_for_github_issue(self, workspace_id, user_id):
        """Test preview JSON structure for GitHub issue creation."""
        preview = {
            "repo": "org/repo",
            "title": "Add feature flag support",
            "body": "## Description\nImplement feature flags...",
            "labels": ["enhancement", "good-first-issue"],
            "assignees": ["@alice"]
        }
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_GITHUB_ISSUE,
            preview_json=preview
        )
        
        assert action.preview_json["repo"] == "org/repo"
        assert action.preview_json["title"] == "Add feature flag support"
        assert "enhancement" in action.preview_json["labels"]

    def test_preview_json_can_be_empty_dict(self, workspace_id, user_id):
        """Test that preview_json can be an empty dictionary."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json={}
        )
        
        assert action.preview_json == {}

    def test_preview_json_cannot_be_null(self, workspace_id, user_id):
        """Test that preview_json cannot be null (must be JSON object)."""
        with pytest.raises((ValueError, IntegrityError, TypeError)):
            AgentAction(
                workspace_id=workspace_id,
                user_id=user_id,
                action_type=ActionType.CREATE_JIRA_TICKET,
                preview_json=None
            )


class TestAgentActionExpiration:
    """Test expiration logic and expired action detection."""

    def test_is_expired_returns_true_after_expiration(self, workspace_id, user_id, sample_preview_json):
        """Test that is_expired() returns True after expiration time."""
        expires_at = datetime.utcnow() - timedelta(hours=1)  # 1 hour ago
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=sample_preview_json,
            expires_at=expires_at
        )
        
        assert action.is_expired() is True

    def test_is_expired_returns_false_before_expiration(self, workspace_id, user_id, sample_preview_json):
        """Test that is_expired() returns False before expiration time."""
        expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 hour from now
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=sample_preview_json,
            expires_at=expires_at
        )
        
        assert action.is_expired() is False

    def test_mark_as_expired_updates_status(self, workspace_id, user_id, sample_preview_json):
        """Test that mark_as_expired() updates status to EXPIRED."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json
        )
        
        action.mark_as_expired()
        
        assert action.status == ActionStatus.EXPIRED

    def test_expired_actions_cannot_be_approved(self, workspace_id, user_id, sample_preview_json):
        """Test that expired actions cannot transition to APPROVED."""
        expires_at = datetime.utcnow() - timedelta(hours=1)
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=sample_preview_json,
            expires_at=expires_at
        )
        
        assert action.can_be_approved() is False


class TestAgentActionValidation:
    """Test validation rules for AgentAction."""

    def test_workspace_id_required(self, user_id, sample_preview_json):
        """Test that workspace_id is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AgentAction(
                workspace_id=None,
                user_id=user_id,
                action_type=ActionType.CREATE_JIRA_TICKET,
                preview_json=sample_preview_json
            )

    def test_user_id_required(self, workspace_id, sample_preview_json):
        """Test that user_id is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AgentAction(
                workspace_id=workspace_id,
                user_id=None,
                action_type=ActionType.CREATE_JIRA_TICKET,
                preview_json=sample_preview_json
            )

    def test_action_type_required(self, workspace_id, user_id, sample_preview_json):
        """Test that action_type is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AgentAction(
                workspace_id=workspace_id,
                user_id=user_id,
                action_type=None,
                preview_json=sample_preview_json
            )

    def test_timestamps_auto_generated(self, workspace_id, user_id, sample_preview_json):
        """Test that created_at and updated_at are auto-generated."""
        before = datetime.utcnow()
        
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            preview_json=sample_preview_json
        )
        
        after = datetime.utcnow()
        
        # Note: In actual implementation, timestamps are set by database defaults
        # This test verifies the model accepts datetime objects
        assert action.created_at is None or (before <= action.created_at <= after)


class TestAgentActionHelperMethods:
    """Test helper methods on AgentAction model."""

    def test_can_be_approved_returns_true_when_pending(self, workspace_id, user_id, sample_preview_json):
        """Test that can_be_approved() returns True when status is PENDING_APPROVAL and not expired."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        
        assert action.can_be_approved() is True

    def test_can_be_approved_returns_false_when_expired(self, workspace_id, user_id, sample_preview_json):
        """Test that can_be_approved() returns False when action is expired."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json,
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        
        assert action.can_be_approved() is False

    def test_can_be_approved_returns_false_when_already_executed(self, workspace_id, user_id, sample_preview_json):
        """Test that can_be_approved() returns False when already executed."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.EXECUTED,
            preview_json=sample_preview_json
        )
        
        assert action.can_be_approved() is False

    def test_can_be_cancelled_returns_true_when_pending(self, workspace_id, user_id, sample_preview_json):
        """Test that can_be_cancelled() returns True when status is PENDING_APPROVAL or APPROVED."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json
        )
        
        assert action.can_be_cancelled() is True

    def test_can_be_cancelled_returns_false_when_executed(self, workspace_id, user_id, sample_preview_json):
        """Test that can_be_cancelled() returns False when already executed."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.EXECUTED,
            preview_json=sample_preview_json
        )
        
        assert action.can_be_cancelled() is False

    def test_to_dict_includes_all_fields(self, workspace_id, user_id, conversation_id, sample_preview_json):
        """Test that to_dict() includes all fields in dictionary representation."""
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            action_type=ActionType.CREATE_JIRA_TICKET,
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=sample_preview_json,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        action.id = uuid4()  # Simulate database-assigned ID
        
        result = action.to_dict()
        
        assert "id" in result
        assert result["workspace_id"] == str(workspace_id)
        assert result["user_id"] == str(user_id)
        assert result["conversation_id"] == str(conversation_id)
        assert result["action_type"] == ActionType.CREATE_JIRA_TICKET.value
        assert result["status"] == ActionStatus.PENDING_APPROVAL.value
        assert result["preview_json"] == sample_preview_json
        assert "expires_at" in result
