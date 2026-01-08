"""
Unit tests for CreateJiraTicketAction handler (T155).

Tests the Jira ticket creation action handler which generates previews and
executes ticket creation with dry-run permission validation.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime

from src.agents.create_jira_ticket import CreateJiraTicketAction, JiraTicketPreview
from src.models.agent_action import ActionType


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
    client = AsyncMock()
    client.get_projects = AsyncMock(return_value=[
        {"key": "PROJ", "name": "Project Alpha"},
        {"key": "TEST", "name": "Test Project"}
    ])
    client.get_issue_types = AsyncMock(return_value=[
        {"id": "10001", "name": "Task"},
        {"id": "10002", "name": "Bug"},
        {"id": "10003", "name": "Story"}
    ])
    client.get_priorities = AsyncMock(return_value=[
        {"id": "1", "name": "Highest"},
        {"id": "2", "name": "High"},
        {"id": "3", "name": "Medium"},
        {"id": "4", "name": "Low"}
    ])
    client.create_issue = AsyncMock(return_value={
        "id": "10100",
        "key": "PROJ-123",
        "self": "https://jira.example.com/rest/api/2/issue/10100"
    })
    client.check_create_permission = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_request():
    """Sample request for Jira ticket creation."""
    return {
        "user_query": "Create a task to implement feature X with high priority",
        "context": {
            "project": "PROJ",
            "suggested_summary": "Implement feature X",
            "suggested_description": "As a user, I want feature X so that I can...",
            "suggested_priority": "High"
        }
    }


class TestJiraTicketPreviewGeneration:
    """Test preview generation for Jira ticket creation."""

    @pytest.mark.asyncio
    async def test_generate_preview_from_user_query(self, workspace_id, user_id, conversation_id, mock_jira_client, sample_request):
        """Test generating preview from natural language query."""
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert isinstance(preview, JiraTicketPreview)
        assert preview.project == "PROJ"
        assert "Implement feature X" in preview.summary
        assert "feature X" in preview.description
        assert preview.priority == "High"

    @pytest.mark.asyncio
    async def test_preview_includes_all_required_fields(self, workspace_id, user_id, conversation_id, mock_jira_client, sample_request):
        """Test that preview includes all required Jira fields."""
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert preview.project is not None
        assert preview.issue_type is not None
        assert preview.summary is not None
        assert preview.description is not None

    @pytest.mark.asyncio
    async def test_preview_defaults_issue_type_to_task(self, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that issue_type defaults to 'Task' when not specified."""
        request = {
            "user_query": "Create ticket for implementing auth",
            "context": {"project": "PROJ"}
        }
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=request
        )
        
        assert preview.issue_type == "Task"

    @pytest.mark.asyncio
    async def test_preview_extracts_priority_from_query(self, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that priority is extracted from query keywords."""
        high_priority_request = {
            "user_query": "URGENT: Fix critical login bug",
            "context": {"project": "PROJ"}
        }
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=high_priority_request
        )
        
        # Priority should be High or Highest for urgent/critical keywords
        assert preview.priority in ["High", "Highest"]

    @pytest.mark.asyncio
    async def test_preview_includes_ai_generated_label(self, workspace_id, user_id, conversation_id, mock_jira_client, sample_request):
        """Test that preview automatically includes 'ai-generated' label."""
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert "ai-generated" in preview.labels

    @pytest.mark.asyncio
    async def test_preview_allows_user_specified_labels(self, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that user-specified labels are included in preview."""
        request = {
            "user_query": "Create task",
            "context": {
                "project": "PROJ",
                "labels": ["security", "q1-2026"]
            }
        }
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=request
        )
        
        assert "security" in preview.labels
        assert "q1-2026" in preview.labels
        assert "ai-generated" in preview.labels

    @pytest.mark.asyncio
    async def test_preview_validates_project_exists(self, workspace_id, user_id, conversation_id, mock_jira_client):
        """Test that preview validation checks if project exists."""
        invalid_request = {
            "user_query": "Create task",
            "context": {"project": "INVALID"}
        }
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        with pytest.raises(ValueError, match="Project.*not found"):
            await action.generate_preview(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=invalid_request
            )


class TestJiraTicketExecution:
    """Test execution of Jira ticket creation."""

    @pytest.mark.asyncio
    async def test_execute_creates_jira_ticket(self, workspace_id, user_id, mock_jira_client):
        """Test that execute() creates actual Jira ticket."""
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Task",
            summary="Implement feature X",
            description="As a user, I want feature X...",
            priority="High",
            labels=["ai-generated"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is True
        assert result.ticket_key == "PROJ-123"
        assert result.ticket_url == "https://jira.example.com/browse/PROJ-123"
        
        # Verify Jira API was called with correct parameters
        mock_jira_client.create_issue.assert_called_once()
        call_args = mock_jira_client.create_issue.call_args[1]
        assert call_args["project"] == "PROJ"
        assert call_args["summary"] == "Implement feature X"

    @pytest.mark.asyncio
    async def test_execute_returns_ticket_url(self, workspace_id, user_id, mock_jira_client):
        """Test that execute() returns ticket URL for result_url field."""
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Bug",
            summary="Fix login issue",
            description="Users cannot log in",
            priority="Highest",
            labels=["ai-generated", "security"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert "https://jira.example.com/browse/PROJ-123" in result.ticket_url

    @pytest.mark.asyncio
    async def test_execute_includes_all_preview_fields(self, workspace_id, user_id, mock_jira_client):
        """Test that execute() includes all fields from preview."""
        preview = JiraTicketPreview(
            project="TEST",
            issue_type="Story",
            summary="User story for login",
            description="Acceptance criteria:\n- User can log in\n- Session persists",
            priority="Medium",
            assignee="john.doe@example.com",
            labels=["ai-generated", "sprint-1"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        call_args = mock_jira_client.create_issue.call_args[1]
        assert call_args["project"] == "TEST"
        assert call_args["issue_type"] == "Story"
        assert call_args["summary"] == "User story for login"
        assert call_args["priority"] == "Medium"
        assert call_args["assignee"] == "john.doe@example.com"
        assert "sprint-1" in call_args["labels"]

    @pytest.mark.asyncio
    async def test_execute_handles_jira_api_errors(self, workspace_id, user_id, mock_jira_client):
        """Test that execute() handles Jira API errors gracefully."""
        mock_jira_client.create_issue.side_effect = Exception("Jira API returned 401: Unauthorized")
        
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Task",
            summary="Test task",
            description="Test description",
            priority="Medium",
            labels=["ai-generated"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is False
        assert "Unauthorized" in result.error_message


class TestJiraPermissionChecks:
    """Test dry-run permission validation."""

    @pytest.mark.asyncio
    async def test_check_permissions_validates_create_access(self, workspace_id, user_id, mock_jira_client):
        """Test that permission check validates user can create issues."""
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Task",
            summary="Test task",
            description="Test description",
            priority="Medium",
            labels=["ai-generated"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is True
        mock_jira_client.check_create_permission.assert_called_once_with(
            project="PROJ",
            issue_type="Task",
            user_id=str(user_id)
        )

    @pytest.mark.asyncio
    async def test_check_permissions_returns_false_when_no_access(self, workspace_id, user_id, mock_jira_client):
        """Test that permission check returns False when user lacks access."""
        mock_jira_client.check_create_permission.return_value = False
        
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Task",
            summary="Test task",
            description="Test description",
            priority="Medium",
            labels=["ai-generated"]
        )
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is False

    @pytest.mark.asyncio
    async def test_check_permissions_validates_project_access(self, workspace_id, user_id, mock_jira_client):
        """Test that permission check validates project-specific access."""
        preview = JiraTicketPreview(
            project="RESTRICTED",
            issue_type="Task",
            summary="Test task",
            description="Test description",
            priority="Medium",
            labels=["ai-generated"]
        )
        
        mock_jira_client.check_create_permission.return_value = False
        
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is False


class TestJiraTicketPreviewModel:
    """Test JiraTicketPreview data model."""

    def test_preview_model_with_all_fields(self):
        """Test creating preview model with all fields."""
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Task",
            summary="Implement feature X",
            description="Detailed description...",
            priority="High",
            assignee="john.doe@example.com",
            labels=["ai-generated", "sprint-1"],
            components=["Backend", "API"],
            custom_fields={"customfield_10001": "value"}
        )
        
        assert preview.project == "PROJ"
        assert preview.issue_type == "Task"
        assert preview.summary == "Implement feature X"
        assert preview.priority == "High"
        assert "Backend" in preview.components
        assert "customfield_10001" in preview.custom_fields

    def test_preview_model_to_dict(self):
        """Test converting preview to dictionary."""
        preview = JiraTicketPreview(
            project="PROJ",
            issue_type="Bug",
            summary="Fix login",
            description="Login broken",
            priority="Highest",
            labels=["ai-generated"]
        )
        
        result = preview.to_dict()
        
        assert result["project"] == "PROJ"
        assert result["issue_type"] == "Bug"
        assert result["summary"] == "Fix login"
        assert "ai-generated" in result["labels"]

    def test_preview_model_from_dict(self):
        """Test creating preview from dictionary."""
        data = {
            "project": "TEST",
            "issue_type": "Story",
            "summary": "User story",
            "description": "As a user...",
            "priority": "Medium",
            "labels": ["ai-generated"]
        }
        
        preview = JiraTicketPreview.from_dict(data)
        
        assert preview.project == "TEST"
        assert preview.issue_type == "Story"
        assert preview.summary == "User story"

    def test_preview_model_validates_required_fields(self):
        """Test that preview validates required fields."""
        with pytest.raises((ValueError, TypeError)):
            JiraTicketPreview(
                project=None,  # Required field
                issue_type="Task",
                summary="Test",
                description="Test",
                priority="Medium",
                labels=[]
            )


class TestJiraActionIntegration:
    """Test end-to-end integration of Jira action handler."""

    @pytest.mark.asyncio
    async def test_full_workflow_generate_to_execute(self, workspace_id, user_id, conversation_id, mock_jira_client, sample_request):
        """Test complete workflow from preview generation to execution."""
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        # 1. Generate preview
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert preview.summary == "Implement feature X"
        
        # 2. Check permissions
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is True
        
        # 3. Execute action
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is True
        assert result.ticket_key == "PROJ-123"

    @pytest.mark.asyncio
    async def test_workflow_with_preview_edit(self, workspace_id, user_id, conversation_id, mock_jira_client, sample_request):
        """Test workflow with user editing preview before approval."""
        action = CreateJiraTicketAction(jira_client=mock_jira_client)
        
        # Generate initial preview
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        # User edits preview
        preview.summary = "Updated: Implement feature X with tests"
        preview.priority = "Highest"
        preview.labels.append("testing")
        
        # Execute with edited preview
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is True
        
        # Verify edited fields were used
        call_args = mock_jira_client.create_issue.call_args[1]
        assert call_args["summary"] == "Updated: Implement feature X with tests"
        assert call_args["priority"] == "Highest"
        assert "testing" in call_args["labels"]
