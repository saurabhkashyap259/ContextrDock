"""
End-to-end scenario tests for Phase 7 (T176-T180).

Tests complete workflows from action creation through execution and audit logging.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timedelta

from src.models.agent_action import AgentAction, ActionStatus
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
def conversation_id():
    """Sample conversation ID."""
    return uuid4()


@pytest.fixture
def mock_jira_client():
    """Mock Jira API client with successful responses."""
    client = Mock()
    client.get_projects = AsyncMock(return_value=[
        {"key": "PROJ", "name": "Test Project"}
    ])
    client.get_issue_types = AsyncMock(return_value=[
        {"name": "Task"}, {"name": "Bug"}
    ])
    client.get_priorities = AsyncMock(return_value=[
        {"name": "High"}, {"name": "Medium"}
    ])
    client.check_create_permission = AsyncMock(return_value=True)
    client.create_issue = AsyncMock(return_value={
        "key": "PROJ-123",
        "url": "https://jira.example.com/browse/PROJ-123"
    })
    return client


@pytest.fixture
def mock_confluence_client():
    """Mock Confluence API client with successful responses."""
    client = Mock()
    client.get_spaces = AsyncMock(return_value=[
        {"key": "TEAM", "name": "Team Space"}
    ])
    client.check_create_permission = AsyncMock(return_value=True)
    client.create_page = AsyncMock(return_value={
        "id": "12345",
        "url": "https://confluence.example.com/pages/12345"
    })
    return client


@pytest.fixture
def mock_github_client():
    """Mock GitHub API client with successful responses."""
    client = Mock()
    client.get_repository = AsyncMock(return_value={
        "full_name": "org/repo",
        "permissions": {"admin": True}
    })
    client.check_create_permission = AsyncMock(return_value=True)
    client.create_issue = AsyncMock(return_value={
        "number": 42,
        "url": "https://github.com/org/repo/issues/42"
    })
    return client


class TestScenario1GeneratePreview:
    """
    Scenario 1: Generate preview (T176).
    
    User creates an action, system generates preview, user reviews.
    """

    @pytest.mark.asyncio
    async def test_create_jira_action_and_verify_preview(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test generating Jira ticket preview from natural language."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            # Mock preview generation
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Bug",
                "summary": "Fix critical login bug",
                "description": "Users unable to login after password reset",
                "priority": "High",
                "labels": ["ai-generated", "urgent"]
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            # Create action
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a high-priority Jira bug ticket: Users can't login after password reset. This is critical!",
                    "context": {"project": "PROJ"},
                    "conversation_id": str(conversation_id)
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            # Verify action created with preview
            assert response.status_code == 201
            data = response.json()
            
            assert data["action_type"] == "create_jira_ticket"
            assert data["status"] == "pending_approval"
            assert data["workspace_id"] == str(workspace_id)
            assert data["user_id"] == str(user_id)
            assert data["conversation_id"] == str(conversation_id)
            
            # Verify preview fields
            preview = data["preview_json"]
            assert preview["project"] == "PROJ"
            assert preview["issue_type"] == "Bug"
            assert preview["summary"] == "Fix critical login bug"
            assert preview["priority"] == "High"
            assert "ai-generated" in preview["labels"]
            assert "urgent" in preview["labels"]
            
            # Verify expiration set (24 hours)
            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            expected_expires = datetime.utcnow() + timedelta(hours=24)
            assert abs((expires_at - expected_expires).total_seconds()) < 60  # Within 1 minute
            
            # Verify URLs are null (not executed yet)
            assert data["result_url"] is None
            assert data["error_message"] is None

    @pytest.mark.asyncio
    async def test_create_confluence_action_and_verify_preview(self, client, workspace_id, user_id, mock_confluence_client):
        """Test generating Confluence page preview from natural language."""
        with patch('src.agents.create_confluence_page.CreateConfluencePageAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "space": "TEAM",
                "title": "Q4 2024 Product Roadmap",
                "body": "<h1>Q4 2024 Product Roadmap</h1><p>Key initiatives...</p>",
                "labels": ["ai-generated", "roadmap"]
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_confluence_page",
                    "user_query": "Create a Confluence page for Q4 2024 Product Roadmap in TEAM space",
                    "context": {"space": "TEAM"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            
            assert data["action_type"] == "create_confluence_page"
            assert data["status"] == "pending_approval"
            
            preview = data["preview_json"]
            assert preview["space"] == "TEAM"
            assert preview["title"] == "Q4 2024 Product Roadmap"
            assert "ai-generated" in preview["labels"]

    @pytest.mark.asyncio
    async def test_create_github_action_and_verify_preview(self, client, workspace_id, user_id, mock_github_client):
        """Test generating GitHub issue preview from natural language."""
        with patch('src.agents.create_github_issue.CreateGitHubIssueAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "repo": "org/repo",
                "title": "Add support for dark mode",
                "body": "Users are requesting dark mode support",
                "labels": ["ai-generated", "enhancement"]
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_github_issue",
                    "user_query": "Create a GitHub issue to add dark mode support for org/repo",
                    "context": {"repo": "org/repo"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            
            assert data["action_type"] == "create_github_issue"
            preview = data["preview_json"]
            assert preview["repo"] == "org/repo"
            assert preview["title"] == "Add support for dark mode"


class TestScenario2EditAndApprove:
    """
    Scenario 2: Edit and approve (T177).
    
    User creates action, edits preview, approves, system executes.
    """

    @pytest.mark.asyncio
    async def test_complete_workflow_with_preview_edit(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test complete workflow: create → edit preview → approve → execute."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            # Setup mock action handler
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Update documentation",
                "description": "API docs need updates",
                "priority": "Medium"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action.execute = AsyncMock(return_value=Mock(
                success=True,
                ticket_key="PROJ-123",
                ticket_url="https://jira.example.com/browse/PROJ-123",
                error_message=None
            ))
            mock_action_class.return_value = mock_action
            
            # Step 1: Create action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira task to update documentation",
                    "context": {"project": "PROJ"},
                    "conversation_id": str(conversation_id)
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert create_response.status_code == 201
            action_data = create_response.json()
            action_id = action_data["id"]
            
            # Verify initial preview
            assert action_data["preview_json"]["priority"] == "Medium"
            assert action_data["preview_json"]["summary"] == "Update documentation"
            
            # Step 2: Retrieve action to review
            get_response = client.get(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert get_response.status_code == 200
            assert get_response.json()["status"] == "pending_approval"
            
            # Step 3: Approve with edited preview (user changed priority and summary)
            edited_preview = {
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Update API documentation with authentication examples",
                "description": "API docs need updates",
                "priority": "High"  # Changed from Medium to High
            }
            
            approve_response = client.post(
                f"/v1/actions/{action_id}/approve",
                json={"edited_preview": edited_preview},
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert approve_response.status_code == 200
            execution_data = approve_response.json()
            
            # Verify execution successful
            assert execution_data["status"] == "executed"
            assert execution_data["result_url"] == "https://jira.example.com/browse/PROJ-123"
            assert execution_data["error_message"] is None
            
            # Step 4: Verify final state
            final_response = client.get(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            final_data = final_response.json()
            assert final_data["status"] == "executed"
            assert final_data["result_url"] == "https://jira.example.com/browse/PROJ-123"
            
            # Verify edited preview was saved
            assert final_data["preview_json"]["priority"] == "High"
            assert "authentication examples" in final_data["preview_json"]["summary"]

    @pytest.mark.asyncio
    async def test_approve_without_edits(self, client, workspace_id, user_id, mock_confluence_client):
        """Test approval without editing preview."""
        with patch('src.agents.create_confluence_page.CreateConfluencePageAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "space": "TEAM",
                "title": "Meeting Notes",
                "body": "<p>Notes here</p>"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action.execute = AsyncMock(return_value=Mock(
                success=True,
                page_id="12345",
                page_url="https://confluence.example.com/pages/12345",
                error_message=None
            ))
            mock_action_class.return_value = mock_action
            
            # Create action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_confluence_page",
                    "user_query": "Create meeting notes page",
                    "context": {"space": "TEAM"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            action_id = create_response.json()["id"]
            
            # Approve without edits
            approve_response = client.post(
                f"/v1/actions/{action_id}/approve",
                json={},  # No edited_preview
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert approve_response.status_code == 200
            assert approve_response.json()["status"] == "executed"


class TestScenario3CancelAction:
    """
    Scenario 3: Cancel action (T178).
    
    User creates action, then cancels before approval.
    """

    @pytest.mark.asyncio
    async def test_cancel_pending_action(self, client, workspace_id, user_id, mock_jira_client):
        """Test cancelling action before approval."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test task",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            # Create action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a test task",
                    "context": {"project": "PROJ"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            action_id = create_response.json()["id"]
            assert create_response.json()["status"] == "pending_approval"
            
            # Cancel action
            cancel_response = client.delete(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert cancel_response.status_code == 204
            
            # Verify action is cancelled
            get_response = client.get(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert get_response.json()["status"] == "cancelled"
            assert get_response.json()["result_url"] is None

    @pytest.mark.asyncio
    async def test_cannot_cancel_executed_action(self, client, workspace_id, user_id, mock_jira_client):
        """Test that executed actions cannot be cancelled."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action.execute = AsyncMock(return_value=Mock(
                success=True,
                ticket_key="PROJ-123",
                ticket_url="https://jira.example.com/browse/PROJ-123",
                error_message=None
            ))
            mock_action_class.return_value = mock_action
            
            # Create and execute action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a test task",
                    "context": {"project": "PROJ"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            action_id = create_response.json()["id"]
            
            # Approve (execute)
            client.post(
                f"/v1/actions/{action_id}/approve",
                json={},
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            # Try to cancel - should fail
            cancel_response = client.delete(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert cancel_response.status_code == 400
            assert "cannot be cancelled" in cancel_response.json()["detail"].lower()


class TestScenario4AuditLogEntry:
    """
    Scenario 4: Audit log entry (T179).
    
    Complete action workflow generates comprehensive audit trail.
    """

    @pytest.mark.asyncio
    async def test_complete_audit_trail(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that complete workflow generates all audit log entries."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action.execute = AsyncMock(return_value=Mock(
                success=True,
                ticket_key="PROJ-123",
                ticket_url="https://jira.example.com/browse/PROJ-123",
                error_message=None
            ))
            mock_action_class.return_value = mock_action
            
            # Create action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a test task",
                    "context": {"project": "PROJ"},
                    "conversation_id": str(conversation_id)
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            action_id = create_response.json()["id"]
            
            # Approve action
            client.post(
                f"/v1/actions/{action_id}/approve",
                json={},
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            # Retrieve audit logs
            audit_response = client.get(
                f"/v1/admin/audit-logs?target_type=AgentAction&target_id={action_id}",
                headers={
                    "X-Workspace-ID": str(workspace_id),
                    "X-User-ID": str(user_id),
                    "X-User-Role": "admin"
                }
            )
            
            assert audit_response.status_code == 200
            audit_data = audit_response.json()
            
            # Verify audit log entries
            logs = audit_data["items"]
            actions = [log["action"] for log in logs]
            
            # Should have: created, approved, executed
            assert "action.created" in actions
            assert "action.approved" in actions
            assert "action.executed" in actions
            
            # Verify log details
            created_log = next(log for log in logs if log["action"] == "action.created")
            assert created_log["actor_user_id"] == str(user_id)
            assert created_log["actor_type"] == "user"
            assert created_log["details_json"]["action_type"] == "create_jira_ticket"
            
            approved_log = next(log for log in logs if log["action"] == "action.approved")
            assert approved_log["actor_user_id"] == str(user_id)
            assert "preview_edited" in approved_log["details_json"]
            
            executed_log = next(log for log in logs if log["action"] == "action.executed")
            assert executed_log["actor_user_id"] is None  # System event
            assert executed_log["actor_type"] == "system"
            assert "result_url" in executed_log["details_json"]
            assert executed_log["details_json"]["result_url"] == "https://jira.example.com/browse/PROJ-123"

    @pytest.mark.asyncio
    async def test_cancellation_audit_trail(self, client, workspace_id, user_id, mock_jira_client):
        """Test audit trail for cancelled action."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            # Create action
            create_response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a test task",
                    "context": {}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            action_id = create_response.json()["id"]
            
            # Cancel action
            client.delete(
                f"/v1/actions/{action_id}",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            # Check audit logs
            audit_response = client.get(
                f"/v1/admin/audit-logs?target_id={action_id}",
                headers={
                    "X-Workspace-ID": str(workspace_id),
                    "X-User-ID": str(user_id),
                    "X-User-Role": "admin"
                }
            )
            
            logs = audit_response.json()["items"]
            actions = [log["action"] for log in logs]
            
            assert "action.created" in actions
            assert "action.cancelled" in actions
            assert "action.executed" not in actions  # Should not be executed


class TestScenario5PermissionError:
    """
    Scenario 5: Permission error (T180).
    
    User attempts to create action for restricted resource, receives permission error.
    """

    @pytest.mark.asyncio
    async def test_permission_denied_during_creation(self, client, workspace_id, user_id):
        """Test permission error during action creation."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "RESTRICTED",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=False)  # Permission denied
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a task in restricted project",
                    "context": {"project": "RESTRICTED"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 403
            assert "permission" in response.json()["detail"].lower()
            
            # Verify no action was created
            list_response = client.get(
                "/v1/actions",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            actions = list_response.json()["items"]
            restricted_actions = [a for a in actions if a["preview_json"].get("project") == "RESTRICTED"]
            assert len(restricted_actions) == 0

    @pytest.mark.asyncio
    async def test_permission_error_prevents_execution(self, client, workspace_id, user_id):
        """Test that permission check prevents action creation (no orphan actions)."""
        with patch('src.agents.create_github_issue.CreateGitHubIssueAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "repo": "secret/private-repo",
                "title": "Test issue",
                "body": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=False)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_github_issue",
                    "user_query": "Create issue in private repo",
                    "context": {"repo": "secret/private-repo"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 403
            
            # Verify action was NOT created in database
            list_response = client.get(
                "/v1/actions?page_size=100",
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            all_actions = list_response.json()["items"]
            private_repo_actions = [
                a for a in all_actions 
                if a["action_type"] == "create_github_issue" 
                and a["preview_json"].get("repo") == "secret/private-repo"
            ]
            
            assert len(private_repo_actions) == 0
