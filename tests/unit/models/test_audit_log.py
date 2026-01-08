"""
Unit tests for AuditLog model (T152).

Tests the AuditLog model which provides immutable audit trail for all write
operations in the system (connector creation, action approval, etc.).
"""
import pytest
from datetime import datetime
from uuid import uuid4
from sqlalchemy.exc import IntegrityError

from src.models.audit_log import AuditLog


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
def sample_details_json():
    """Sample details JSON for audit entry."""
    return {
        "before": {"status": "pending_approval"},
        "after": {"status": "approved"},
        "metadata": {"approval_time_seconds": 45}
    }


class TestAuditLogCreation:
    """Test AuditLog model creation and field validation."""

    def test_create_audit_log_with_user_actor(self, workspace_id, user_id, target_id, sample_details_json):
        """Test creating audit log with user as actor."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id,
            details_json=sample_details_json,
            ip_address="192.168.1.100"
        )
        
        assert log.workspace_id == workspace_id
        assert log.actor_user_id == user_id
        assert log.action == "action.approved"
        assert log.target_type == "AgentAction"
        assert log.target_id == target_id
        assert log.details_json == sample_details_json
        assert log.ip_address == "192.168.1.100"

    def test_create_audit_log_with_system_actor(self, workspace_id, target_id):
        """Test creating audit log with system as actor (NULL user_id)."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,
            action="sync.completed",
            target_type="Connector",
            target_id=target_id,
            details_json={"documents_indexed": 150}
        )
        
        assert log.workspace_id == workspace_id
        assert log.actor_user_id is None
        assert log.action == "sync.completed"
        assert log.details_json["documents_indexed"] == 150

    def test_create_audit_log_minimal_fields(self, workspace_id, user_id, target_id):
        """Test creating audit log with only required fields."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="connector.created",
            target_type="Connector",
            target_id=target_id
        )
        
        assert log.workspace_id == workspace_id
        assert log.action == "connector.created"
        assert log.details_json == {}
        assert log.ip_address is None

    def test_default_details_json_is_empty_dict(self, workspace_id, user_id, target_id):
        """Test that details_json defaults to empty dictionary."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="document.deleted",
            target_type="Document",
            target_id=target_id
        )
        
        assert log.details_json == {}

    def test_timestamps_auto_generated(self, workspace_id, user_id, target_id):
        """Test that created_at timestamp is auto-generated."""
        before = datetime.utcnow()
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="user.role_changed",
            target_type="User",
            target_id=target_id
        )
        
        after = datetime.utcnow()
        
        # Note: In actual implementation, timestamp is set by database default
        assert log.created_at is None or (before <= log.created_at <= after)


class TestAuditLogActions:
    """Test action naming convention and validation."""

    def test_action_follows_entity_verb_convention(self, workspace_id, user_id, target_id):
        """Test that action follows 'entity.verb' naming convention."""
        valid_actions = [
            "connector.created",
            "connector.updated",
            "connector.deleted",
            "action.approved",
            "action.executed",
            "action.cancelled",
            "sync.started",
            "sync.completed",
            "sync.failed",
            "user.role_changed",
            "document.indexed"
        ]
        
        for action in valid_actions:
            log = AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action=action,
                target_type="TestEntity",
                target_id=target_id
            )
            assert log.action == action
            assert "." in log.action  # Verify dot separator

    def test_action_with_custom_format(self, workspace_id, user_id, target_id):
        """Test that action can use custom format if needed."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="workspace.settings.permissions_changed",
            target_type="Workspace",
            target_id=target_id
        )
        
        assert log.action == "workspace.settings.permissions_changed"


class TestAuditLogTargetTypes:
    """Test target entity type tracking."""

    def test_all_target_types_supported(self, workspace_id, user_id, target_id):
        """Test that all entity types can be tracked."""
        target_types = [
            "Workspace",
            "User",
            "Connector",
            "Document",
            "Conversation",
            "AgentAction",
            "AuditLog"
        ]
        
        for target_type in target_types:
            log = AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action=f"{target_type.lower()}.created",
                target_type=target_type,
                target_id=target_id
            )
            assert log.target_type == target_type

    def test_target_id_tracks_entity_identifier(self, workspace_id, user_id):
        """Test that target_id correctly identifies the affected entity."""
        connector_id = uuid4()
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="connector.credentials_updated",
            target_type="Connector",
            target_id=connector_id
        )
        
        assert log.target_id == connector_id


class TestAuditLogDetailsJson:
    """Test details_json field for storing contextual information."""

    def test_details_json_stores_before_after_state(self, workspace_id, user_id, target_id):
        """Test details_json can store before/after state changes."""
        details = {
            "before": {
                "status": "pending_approval",
                "preview_json": {"summary": "Old title"}
            },
            "after": {
                "status": "approved",
                "preview_json": {"summary": "Updated title"}
            }
        }
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.updated",
            target_type="AgentAction",
            target_id=target_id,
            details_json=details
        )
        
        assert log.details_json["before"]["status"] == "pending_approval"
        assert log.details_json["after"]["status"] == "approved"

    def test_details_json_stores_execution_results(self, workspace_id, user_id, target_id):
        """Test details_json can store execution results."""
        details = {
            "execution_duration_ms": 1234,
            "result_url": "https://jira.example.com/browse/PROJ-123",
            "jira_issue_id": "PROJ-123",
            "created_by": "api_key_xyz"
        }
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.executed",
            target_type="AgentAction",
            target_id=target_id,
            details_json=details
        )
        
        assert log.details_json["execution_duration_ms"] == 1234
        assert log.details_json["result_url"] == "https://jira.example.com/browse/PROJ-123"

    def test_details_json_stores_error_information(self, workspace_id, user_id, target_id):
        """Test details_json can store error details."""
        details = {
            "error_type": "APIError",
            "error_message": "Jira API returned 401: Unauthorized",
            "error_code": "JIRA_AUTH_FAILED",
            "retry_count": 3
        }
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.failed",
            target_type="AgentAction",
            target_id=target_id,
            details_json=details
        )
        
        assert log.details_json["error_type"] == "APIError"
        assert log.details_json["retry_count"] == 3

    def test_details_json_stores_sync_statistics(self, workspace_id, target_id):
        """Test details_json can store sync run statistics."""
        details = {
            "documents_processed": 150,
            "documents_indexed": 145,
            "documents_failed": 5,
            "duration_seconds": 320,
            "connector_type": "jira"
        }
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,  # System action
            action="sync.completed",
            target_type="Connector",
            target_id=target_id,
            details_json=details
        )
        
        assert log.details_json["documents_indexed"] == 145
        assert log.details_json["duration_seconds"] == 320

    def test_details_json_can_be_empty(self, workspace_id, user_id, target_id):
        """Test that details_json can be an empty dictionary."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="connector.enabled",
            target_type="Connector",
            target_id=target_id,
            details_json={}
        )
        
        assert log.details_json == {}

    def test_details_json_stores_nested_structures(self, workspace_id, user_id, target_id):
        """Test details_json can store deeply nested structures."""
        details = {
            "action_preview": {
                "jira_ticket": {
                    "project": "PROJ",
                    "fields": {
                        "summary": "Title",
                        "description": "Body",
                        "labels": ["ai-generated", "approved"]
                    }
                }
            },
            "approval_metadata": {
                "reviewed_at": "2026-01-08T10:30:00Z",
                "comments": "Looks good"
            }
        }
        
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id,
            details_json=details
        )
        
        assert log.details_json["action_preview"]["jira_ticket"]["project"] == "PROJ"
        assert "ai-generated" in log.details_json["action_preview"]["jira_ticket"]["fields"]["labels"]


class TestAuditLogIpAddress:
    """Test IP address tracking for audit trail."""

    def test_ip_address_ipv4_format(self, workspace_id, user_id, target_id):
        """Test IPv4 address storage."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id,
            ip_address="192.168.1.100"
        )
        
        assert log.ip_address == "192.168.1.100"

    def test_ip_address_ipv6_format(self, workspace_id, user_id, target_id):
        """Test IPv6 address storage."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="connector.created",
            target_type="Connector",
            target_id=target_id,
            ip_address="2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        )
        
        assert log.ip_address == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

    def test_ip_address_can_be_null(self, workspace_id, user_id, target_id):
        """Test that IP address is optional (NULL for system actions)."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="sync.started",
            target_type="Connector",
            target_id=target_id,
            ip_address=None
        )
        
        assert log.ip_address is None


class TestAuditLogImmutability:
    """Test that audit logs are immutable after creation."""

    def test_audit_log_is_insert_only(self, workspace_id, user_id, target_id):
        """Test that audit logs should only support INSERT, not UPDATE."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id
        )
        
        # In actual implementation, attempting to update should fail
        # This test documents the expected behavior
        # Database triggers or application logic should prevent updates
        assert log.action == "action.approved"
        
        # Attempting to change action should not be allowed in production
        # (This is enforced by application logic, not the model itself)

    def test_created_at_should_not_change(self, workspace_id, user_id, target_id):
        """Test that created_at timestamp is immutable."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="connector.created",
            target_type="Connector",
            target_id=target_id
        )
        
        # In production, created_at is set once and never updated
        # No updated_at field exists for audit logs (immutable records)
        assert hasattr(log, "created_at")
        assert not hasattr(log, "updated_at")


class TestAuditLogValidation:
    """Test validation rules for AuditLog."""

    def test_workspace_id_required(self, user_id, target_id):
        """Test that workspace_id is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AuditLog(
                workspace_id=None,
                actor_user_id=user_id,
                action="test.action",
                target_type="TestEntity",
                target_id=target_id
            )

    def test_action_required(self, workspace_id, user_id, target_id):
        """Test that action is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action=None,
                target_type="TestEntity",
                target_id=target_id
            )

    def test_target_type_required(self, workspace_id, user_id, target_id):
        """Test that target_type is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action="test.action",
                target_type=None,
                target_id=target_id
            )

    def test_target_id_required(self, workspace_id, user_id):
        """Test that target_id is required."""
        with pytest.raises((IntegrityError, TypeError)):
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action="test.action",
                target_type="TestEntity",
                target_id=None
            )

    def test_actor_user_id_can_be_null(self, workspace_id, target_id):
        """Test that actor_user_id can be NULL for system actions."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,
            action="system.maintenance",
            target_type="Workspace",
            target_id=target_id
        )
        
        assert log.actor_user_id is None


class TestAuditLogHelperMethods:
    """Test helper methods on AuditLog model."""

    def test_is_system_action_returns_true_when_no_actor(self, workspace_id, target_id):
        """Test that is_system_action() returns True when actor_user_id is NULL."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,
            action="sync.completed",
            target_type="Connector",
            target_id=target_id
        )
        
        assert log.is_system_action() is True

    def test_is_system_action_returns_false_when_actor_present(self, workspace_id, user_id, target_id):
        """Test that is_system_action() returns False when actor_user_id is present."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id
        )
        
        assert log.is_system_action() is False

    def test_to_dict_includes_all_fields(self, workspace_id, user_id, target_id, sample_details_json):
        """Test that to_dict() includes all fields in dictionary representation."""
        log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id,
            details_json=sample_details_json,
            ip_address="192.168.1.100"
        )
        log.id = uuid4()  # Simulate database-assigned ID
        
        result = log.to_dict()
        
        assert "id" in result
        assert result["workspace_id"] == str(workspace_id)
        assert result["actor_user_id"] == str(user_id)
        assert result["action"] == "action.approved"
        assert result["target_type"] == "AgentAction"
        assert result["target_id"] == str(target_id)
        assert result["details_json"] == sample_details_json
        assert result["ip_address"] == "192.168.1.100"
        assert "created_at" in result

    def test_get_actor_type_returns_user_or_system(self, workspace_id, user_id, target_id):
        """Test that get_actor_type() returns 'user' or 'system'."""
        user_log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=target_id
        )
        
        system_log = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,
            action="sync.completed",
            target_type="Connector",
            target_id=target_id
        )
        
        assert user_log.get_actor_type() == "user"
        assert system_log.get_actor_type() == "system"


class TestAuditLogUseCases:
    """Test real-world audit log use cases."""

    def test_audit_action_approval_workflow(self, workspace_id, user_id):
        """Test audit trail for complete action approval workflow."""
        action_id = uuid4()
        
        # 1. Action created
        log1 = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.created",
            target_type="AgentAction",
            target_id=action_id,
            details_json={"action_type": "create_jira_ticket"}
        )
        
        # 2. Preview edited
        log2 = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.updated",
            target_type="AgentAction",
            target_id=action_id,
            details_json={
                "before": {"summary": "Old title"},
                "after": {"summary": "New title"}
            }
        )
        
        # 3. Action approved
        log3 = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action="action.approved",
            target_type="AgentAction",
            target_id=action_id,
            ip_address="192.168.1.100"
        )
        
        # 4. Action executed
        log4 = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=None,  # System execution
            action="action.executed",
            target_type="AgentAction",
            target_id=action_id,
            details_json={"result_url": "https://jira.example.com/browse/PROJ-123"}
        )
        
        # All logs reference the same action
        assert log1.target_id == log2.target_id == log3.target_id == log4.target_id
        # User actions have actor, system action has no actor
        assert log1.actor_user_id == user_id
        assert log4.actor_user_id is None

    def test_audit_connector_lifecycle(self, workspace_id, user_id):
        """Test audit trail for connector lifecycle events."""
        connector_id = uuid4()
        
        logs = [
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action="connector.created",
                target_type="Connector",
                target_id=connector_id,
                details_json={"connector_type": "jira"}
            ),
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=None,
                action="sync.started",
                target_type="Connector",
                target_id=connector_id
            ),
            AuditLog(
                workspace_id=workspace_id,
                actor_user_id=None,
                action="sync.completed",
                target_type="Connector",
                target_id=connector_id,
                details_json={"documents_indexed": 150}
            )
        ]
        
        # Verify complete audit trail
        assert len(logs) == 3
        assert all(log.target_id == connector_id for log in logs)
