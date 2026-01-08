"""
Integration tests for POST /v1/actions endpoint (T163).

Tests the action creation endpoint that generates previews and initiates approval workflow.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timedelta

from src.api.schemas.action import ActionCreateRequest


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
    """Mock Jira API client."""
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
    return client


@pytest.fixture
def mock_confluence_client():
    """Mock Confluence API client."""
    client = Mock()
    client.get_spaces = AsyncMock(return_value=[
        {"key": "TEAM", "name": "Team Space"}
    ])
    client.check_create_permission = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_github_client():
    """Mock GitHub API client."""
    client = Mock()
    client.get_repository = AsyncMock(return_value={
        "full_name": "org/repo",
        "permissions": {"admin": True}
    })
    client.check_create_permission = AsyncMock(return_value=True)
    return client


class TestActionCreationBasics:
    """Test basic action creation functionality."""

    @pytest.mark.asyncio
    async def test_create_jira_action_success(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test successful creation of Jira ticket action."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Fix login bug",
                "description": "Users unable to login",
                "priority": "High"
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket to fix the login bug - users are unable to login",
                    "context": {"project": "PROJ"},
                    "conversation_id": str(conversation_id)
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["action_type"] == "create_jira_ticket"
            assert data["status"] == "pending_approval"
            assert data["preview_json"]["project"] == "PROJ"
            assert data["preview_json"]["summary"] == "Fix login bug"
            assert "expires_at" in data
            assert data["workspace_id"] == str(workspace_id)

    @pytest.mark.asyncio
    async def test_create_confluence_action_success(self, client, workspace_id, user_id, mock_confluence_client):
        """Test successful creation of Confluence page action."""
        with patch('src.agents.create_confluence_page.CreateConfluencePageAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "space": "TEAM",
                "title": "API Documentation",
                "body": "<h1>API Docs</h1>",
                "labels": ["ai-generated"]
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_confluence_page",
                    "user_query": "Create a Confluence page for API documentation in TEAM space",
                    "context": {"space": "TEAM"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["action_type"] == "create_confluence_page"
            assert data["preview_json"]["space"] == "TEAM"
            assert "ai-generated" in data["preview_json"]["labels"]

    @pytest.mark.asyncio
    async def test_create_github_action_success(self, client, workspace_id, user_id, mock_github_client):
        """Test successful creation of GitHub issue action."""
        with patch('src.agents.create_github_issue.CreateGitHubIssueAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "repo": "org/repo",
                "title": "Add error handling",
                "body": "Need better error messages",
                "labels": ["ai-generated", "enhancement"]
            })
            mock_action.check_permissions = AsyncMock(return_value=True)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_github_issue",
                    "user_query": "Create a GitHub issue to add error handling for org/repo",
                    "context": {"repo": "org/repo"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["action_type"] == "create_github_issue"
            assert data["preview_json"]["repo"] == "org/repo"


class TestActionCreationValidation:
    """Test request validation for action creation."""

    def test_missing_action_type(self, client, workspace_id, user_id):
        """Test that missing action_type returns 422."""
        response = client.post(
            "/v1/actions",
            json={
                "user_query": "Create something",
                "context": {}
            },
            headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
        )
        
        assert response.status_code == 422
        assert "action_type" in response.json()["detail"][0]["loc"]

    def test_invalid_action_type(self, client, workspace_id, user_id):
        """Test that invalid action_type returns 400."""
        response = client.post(
            "/v1/actions",
            json={
                "action_type": "invalid_action",
                "user_query": "Do something",
                "context": {}
            },
            headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
        )
        
        assert response.status_code == 400
        assert "unsupported" in response.json()["message"].lower()

    def test_missing_user_query(self, client, workspace_id, user_id):
        """Test that missing user_query returns 422."""
        response = client.post(
            "/v1/actions",
            json={
                "action_type": "create_jira_ticket",
                "context": {}
            },
            headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
        )
        
        assert response.status_code == 422

    def test_empty_user_query(self, client, workspace_id, user_id):
        """Test that empty user_query returns 422."""
        response = client.post(
            "/v1/actions",
            json={
                "action_type": "create_jira_ticket",
                "user_query": "",
                "context": {}
            },
            headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
        )
        
        assert response.status_code == 422

    def test_user_query_too_long(self, client, workspace_id, user_id):
        """Test that user_query over 5000 chars returns 422."""
        response = client.post(
            "/v1/actions",
            json={
                "action_type": "create_jira_ticket",
                "user_query": "x" * 5001,
                "context": {}
            },
            headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
        )
        
        assert response.status_code == 422


class TestActionCreationPermissions:
    """Test permission checks during action creation."""

    @pytest.mark.asyncio
    async def test_permission_check_failure(self, client, workspace_id, user_id, mock_jira_client):
        """Test that permission check failure returns 403."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(return_value=False)
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {"project": "PROJ"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 403
            assert "permission" in response.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_permission_check_error(self, client, workspace_id, user_id, mock_jira_client):
        """Test that permission check error returns 500."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(return_value={
                "project": "PROJ",
                "issue_type": "Task",
                "summary": "Test",
                "description": "Test"
            })
            mock_action.check_permissions = AsyncMock(side_effect=Exception("API error"))
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {"project": "PROJ"}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 500


class TestActionCreationAuditLogging:
    """Test audit logging during action creation."""

    @pytest.mark.asyncio
    async def test_creates_audit_log_entry(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that action creation logs to audit trail."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            with patch('src.services.audit_logger.AuditLogger') as mock_audit_logger_class:
                mock_action = Mock()
                mock_action.generate_preview = AsyncMock(return_value={
                    "project": "PROJ",
                    "issue_type": "Task",
                    "summary": "Test",
                    "description": "Test"
                })
                mock_action.check_permissions = AsyncMock(return_value=True)
                mock_action_class.return_value = mock_action
                
                mock_audit_logger = Mock()
                mock_audit_logger.log_action_created = Mock()
                mock_audit_logger_class.return_value = mock_audit_logger
                
                response = client.post(
                    "/v1/actions",
                    json={
                        "action_type": "create_jira_ticket",
                        "user_query": "Create a Jira ticket",
                        "context": {"project": "PROJ"},
                        "conversation_id": str(conversation_id)
                    },
                    headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
                )
                
                assert response.status_code == 201
                mock_audit_logger.log_action_created.assert_called_once()
                call_kwargs = mock_audit_logger.log_action_created.call_args[1]
                assert call_kwargs["action_type"] == "create_jira_ticket"


class TestActionCreationEdgeCases:
    """Test edge cases in action creation."""

    @pytest.mark.asyncio
    async def test_conversation_id_optional(self, client, workspace_id, user_id, mock_jira_client):
        """Test that conversation_id is optional."""
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
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {"project": "PROJ"}
                    # No conversation_id
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            assert data["conversation_id"] is None

    @pytest.mark.asyncio
    async def test_empty_context_allowed(self, client, workspace_id, user_id, mock_jira_client):
        """Test that empty context is allowed."""
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
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket for project PROJ",
                    "context": {}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_preview_generation_error(self, client, workspace_id, user_id, mock_jira_client):
        """Test handling of preview generation errors."""
        with patch('src.agents.create_jira_ticket.CreateJiraTicketAction') as mock_action_class:
            mock_action = Mock()
            mock_action.generate_preview = AsyncMock(side_effect=Exception("Failed to generate preview"))
            mock_action_class.return_value = mock_action
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 500
            assert "preview" in response.json()["message"].lower()


class TestActionCreationResponseFormat:
    """Test response format and fields."""

    @pytest.mark.asyncio
    async def test_response_includes_all_fields(self, client, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that response includes all required fields."""
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
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {"project": "PROJ"},
                    "conversation_id": str(conversation_id)
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            assert response.status_code == 201
            data = response.json()
            
            # Required fields
            assert "id" in data
            assert "workspace_id" in data
            assert "user_id" in data
            assert "conversation_id" in data
            assert "action_type" in data
            assert "status" in data
            assert "preview_json" in data
            assert "expires_at" in data
            assert "created_at" in data
            assert "updated_at" in data
            
            # Optional fields (should be null for new action)
            assert data["result_url"] is None
            assert data["error_message"] is None

    @pytest.mark.asyncio
    async def test_expires_at_is_24_hours_future(self, client, workspace_id, user_id, mock_jira_client):
        """Test that expires_at is set to 24 hours in the future."""
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
            
            before = datetime.utcnow()
            
            response = client.post(
                "/v1/actions",
                json={
                    "action_type": "create_jira_ticket",
                    "user_query": "Create a Jira ticket",
                    "context": {}
                },
                headers={"X-Workspace-ID": str(workspace_id), "X-User-ID": str(user_id)}
            )
            
            after = datetime.utcnow()
            
            assert response.status_code == 201
            data = response.json()
            
            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            expected_min = before + timedelta(hours=23, minutes=59)
            expected_max = after + timedelta(hours=24, minutes=1)
            
            assert expected_min < expires_at < expected_max
