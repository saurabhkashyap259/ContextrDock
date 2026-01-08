"""
Integration tests for GET /v1/admin/audit-logs endpoint (T174).

Tests the admin audit log retrieval endpoint with filtering and pagination.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from uuid import uuid4
from datetime import datetime, timedelta

from src.models.audit_log import AuditLog


@pytest.fixture
def workspace_id():
    """Sample workspace ID."""
    return uuid4()


@pytest.fixture
def admin_user_id():
    """Sample admin user ID."""
    return uuid4()


@pytest.fixture
def regular_user_id():
    """Sample regular user ID."""
    return uuid4()


@pytest.fixture
def action_id():
    """Sample action ID."""
    return uuid4()


class TestAuditLogRetrievalBasics:
    """Test basic audit log retrieval functionality."""

    def test_get_all_audit_logs(self, client, workspace_id, admin_user_id):
        """Test retrieving all audit logs for workspace."""
        response = client.get(
            "/v1/admin/audit-logs",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    def test_get_audit_logs_with_pagination(self, client, workspace_id, admin_user_id):
        """Test pagination of audit logs."""
        response = client.get(
            "/v1/admin/audit-logs?page=2&page_size=10",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["items"]) <= 10

    def test_audit_log_response_format(self, client, workspace_id, admin_user_id):
        """Test that audit log response has all required fields."""
        response = client.get(
            "/v1/admin/audit-logs?page_size=1",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            log = data["items"][0]
            assert "id" in log
            assert "workspace_id" in log
            assert "actor_user_id" in log
            assert "actor_type" in log
            assert "action" in log
            assert "target_type" in log
            assert "target_id" in log
            assert "details_json" in log
            assert "ip_address" in log
            assert "created_at" in log


class TestAuditLogFiltering:
    """Test filtering audit logs by various criteria."""

    def test_filter_by_action(self, client, workspace_id, admin_user_id):
        """Test filtering by action type."""
        response = client.get(
            "/v1/admin/audit-logs?action=action.approved",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            assert log["action"] == "action.approved"

    def test_filter_by_target_type(self, client, workspace_id, admin_user_id):
        """Test filtering by target type."""
        response = client.get(
            "/v1/admin/audit-logs?target_type=AgentAction",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            assert log["target_type"] == "AgentAction"

    def test_filter_by_target_id(self, client, workspace_id, admin_user_id, action_id):
        """Test filtering by specific target entity."""
        response = client.get(
            f"/v1/admin/audit-logs?target_id={action_id}",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            assert log["target_id"] == str(action_id)

    def test_filter_by_actor_user_id(self, client, workspace_id, admin_user_id, regular_user_id):
        """Test filtering by actor user."""
        response = client.get(
            f"/v1/admin/audit-logs?actor_user_id={regular_user_id}",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            if log["actor_user_id"]:  # Skip system events
                assert log["actor_user_id"] == str(regular_user_id)

    def test_filter_by_date_range(self, client, workspace_id, admin_user_id):
        """Test filtering by date range."""
        start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end_date = datetime.utcnow().isoformat()
        
        response = client.get(
            f"/v1/admin/audit-logs?start_date={start_date}&end_date={end_date}",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        
        for log in data["items"]:
            created_at = datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))
            assert start <= created_at <= end

    def test_combine_multiple_filters(self, client, workspace_id, admin_user_id):
        """Test combining multiple filters."""
        response = client.get(
            "/v1/admin/audit-logs?action=action.approved&target_type=AgentAction",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            assert log["action"] == "action.approved"
            assert log["target_type"] == "AgentAction"


class TestAuditLogPermissions:
    """Test permission checks for audit log access."""

    def test_requires_admin_role(self, client, workspace_id, regular_user_id):
        """Test that non-admin users cannot access audit logs."""
        response = client.get(
            "/v1/admin/audit-logs",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(regular_user_id),
                "X-User-Role": "member"
            }
        )
        
        assert response.status_code == 403
        assert "admin" in response.json()["message"].lower()

    def test_missing_role_header(self, client, workspace_id, admin_user_id):
        """Test that missing role header returns 401."""
        response = client.get(
            "/v1/admin/audit-logs",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id)
                # No X-User-Role header
            }
        )
        
        assert response.status_code == 401


class TestAuditLogValidation:
    """Test input validation for audit log filters."""

    def test_invalid_page_number(self, client, workspace_id, admin_user_id):
        """Test that page < 1 returns 422."""
        response = client.get(
            "/v1/admin/audit-logs?page=0",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 422

    def test_invalid_page_size(self, client, workspace_id, admin_user_id):
        """Test that page_size > 200 returns 422."""
        response = client.get(
            "/v1/admin/audit-logs?page_size=201",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 422

    def test_invalid_date_format(self, client, workspace_id, admin_user_id):
        """Test that invalid date format returns 422."""
        response = client.get(
            "/v1/admin/audit-logs?start_date=invalid-date",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 422

    def test_invalid_uuid_format(self, client, workspace_id, admin_user_id):
        """Test that invalid UUID format returns 422."""
        response = client.get(
            "/v1/admin/audit-logs?target_id=not-a-uuid",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 422


class TestAuditLogOrdering:
    """Test ordering and sorting of audit logs."""

    def test_logs_ordered_by_created_at_desc(self, client, workspace_id, admin_user_id):
        """Test that logs are ordered by creation time descending (newest first)."""
        response = client.get(
            "/v1/admin/audit-logs?page_size=10",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) > 1:
            for i in range(len(data["items"]) - 1):
                current = datetime.fromisoformat(data["items"][i]["created_at"].replace("Z", "+00:00"))
                next_item = datetime.fromisoformat(data["items"][i + 1]["created_at"].replace("Z", "+00:00"))
                assert current >= next_item


class TestAuditLogEdgeCases:
    """Test edge cases in audit log retrieval."""

    def test_empty_result_set(self, client, workspace_id, admin_user_id):
        """Test retrieval when no logs match filters."""
        response = client.get(
            "/v1/admin/audit-logs?action=nonexistent.action",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_page_beyond_total(self, client, workspace_id, admin_user_id):
        """Test requesting page number beyond total pages."""
        response = client.get(
            "/v1/admin/audit-logs?page=9999&page_size=10",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    def test_system_events_include_null_actor(self, client, workspace_id, admin_user_id):
        """Test that system events (actor_user_id=None) are included."""
        response = client.get(
            "/v1/admin/audit-logs?action=action.executed",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Look for system events
        system_events = [log for log in data["items"] if log["actor_user_id"] is None]
        if system_events:
            assert system_events[0]["actor_type"] == "system"


class TestAuditLogUseCases:
    """Test real-world audit log use cases."""

    def test_get_action_lifecycle_logs(self, client, workspace_id, admin_user_id, action_id):
        """Test retrieving all logs for an action's lifecycle."""
        response = client.get(
            f"/v1/admin/audit-logs?target_type=AgentAction&target_id={action_id}",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should contain logs for: created, approved, executed
        actions = [log["action"] for log in data["items"]]
        expected_actions = ["action.created", "action.approved", "action.executed"]
        assert any(action in actions for action in expected_actions)

    def test_get_user_activity_history(self, client, workspace_id, admin_user_id, regular_user_id):
        """Test retrieving all activity by a specific user."""
        response = client.get(
            f"/v1/admin/audit-logs?actor_user_id={regular_user_id}",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for log in data["items"]:
            if log["actor_type"] == "user":
                assert log["actor_user_id"] == str(regular_user_id)

    def test_get_recent_workspace_activity(self, client, workspace_id, admin_user_id):
        """Test retrieving recent activity in workspace."""
        response = client.get(
            "/v1/admin/audit-logs?page_size=20",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 20


class TestAuditLogDetailsJson:
    """Test details_json field content."""

    def test_details_json_structure(self, client, workspace_id, admin_user_id):
        """Test that details_json contains expected fields."""
        response = client.get(
            "/v1/admin/audit-logs?page_size=10",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            log = data["items"][0]
            assert isinstance(log["details_json"], dict)

    def test_action_executed_details(self, client, workspace_id, admin_user_id):
        """Test details_json for action.executed events."""
        response = client.get(
            "/v1/admin/audit-logs?action=action.executed",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            log = data["items"][0]
            assert "result_url" in log["details_json"]
            assert "execution_duration_ms" in log["details_json"]

    def test_action_approved_details(self, client, workspace_id, admin_user_id):
        """Test details_json for action.approved events."""
        response = client.get(
            "/v1/admin/audit-logs?action=action.approved",
            headers={
                "X-Workspace-ID": str(workspace_id),
                "X-User-ID": str(admin_user_id),
                "X-User-Role": "admin"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        if data["items"]:
            log = data["items"][0]
            assert "preview_edited" in log["details_json"]
