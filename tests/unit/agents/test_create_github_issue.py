"""
Unit tests for CreateGitHubIssueAction handler (T159).

Tests the GitHub issue creation action handler which generates previews and
executes issue creation with repository permission validation.
"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from src.agents.create_github_issue import CreateGitHubIssueAction, GitHubIssuePreview


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
def mock_github_client():
    """Mock GitHub API client."""
    client = AsyncMock()
    client.get_repositories = AsyncMock(return_value=[
        {"full_name": "org/repo"},
        {"full_name": "org/another-repo"}
    ])
    client.create_issue = AsyncMock(return_value={
        "number": 42,
        "html_url": "https://github.com/org/repo/issues/42"
    })
    client.check_create_permission = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_request():
    """Sample request for GitHub issue creation."""
    return {
        "user_query": "Create issue to add feature flag support",
        "context": {
            "repo": "org/repo",
            "suggested_title": "Add feature flag support",
            "suggested_body": "## Description\nImplement feature flags..."
        }
    }


class TestGitHubIssuePreviewGeneration:
    """Test preview generation for GitHub issue creation."""

    @pytest.mark.asyncio
    async def test_generate_preview_from_user_query(self, workspace_id, user_id, conversation_id, mock_github_client, sample_request):
        """Test generating preview from natural language query."""
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert isinstance(preview, GitHubIssuePreview)
        assert preview.repo == "org/repo"
        assert "feature flag" in preview.title.lower()

    @pytest.mark.asyncio
    async def test_preview_includes_ai_generated_label(self, workspace_id, user_id, conversation_id, mock_github_client, sample_request):
        """Test that preview automatically includes 'ai-generated' label."""
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert "ai-generated" in preview.labels

    @pytest.mark.asyncio
    async def test_preview_validates_repo_exists(self, workspace_id, user_id, conversation_id, mock_github_client):
        """Test that preview validation checks if repository exists."""
        invalid_request = {
            "user_query": "Create issue",
            "context": {"repo": "invalid/repo"}
        }
        
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        
        with pytest.raises(ValueError, match="Repository.*not found"):
            await action.generate_preview(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=invalid_request
            )


class TestGitHubIssueExecution:
    """Test execution of GitHub issue creation."""

    @pytest.mark.asyncio
    async def test_execute_creates_github_issue(self, workspace_id, user_id, mock_github_client):
        """Test that execute() creates actual GitHub issue."""
        preview = GitHubIssuePreview(
            repo="org/repo",
            title="Add feature flag support",
            body="## Description\nImplement feature flags",
            labels=["ai-generated", "enhancement"]
        )
        
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is True
        assert result.issue_number == 42
        assert "https://github.com/org/repo/issues/42" in result.issue_url

    @pytest.mark.asyncio
    async def test_execute_handles_github_api_errors(self, workspace_id, user_id, mock_github_client):
        """Test that execute() handles GitHub API errors gracefully."""
        mock_github_client.create_issue.side_effect = Exception("GitHub API error")
        
        preview = GitHubIssuePreview(
            repo="org/repo",
            title="Test Issue",
            body="Test body",
            labels=["ai-generated"]
        )
        
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is False
        assert "error" in result.error_message.lower()


class TestGitHubPermissionChecks:
    """Test repository permission validation."""

    @pytest.mark.asyncio
    async def test_check_permissions_validates_create_access(self, workspace_id, user_id, mock_github_client):
        """Test that permission check validates user can create issues."""
        preview = GitHubIssuePreview(
            repo="org/repo",
            title="Test Issue",
            body="Test body",
            labels=["ai-generated"]
        )
        
        action = CreateGitHubIssueAction(github_client=mock_github_client)
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is True


class TestGitHubIssuePreviewModel:
    """Test GitHubIssuePreview data model."""

    def test_preview_model_with_assignees(self):
        """Test creating preview with assignees."""
        preview = GitHubIssuePreview(
            repo="org/repo",
            title="Issue with assignees",
            body="Body content",
            labels=["ai-generated"],
            assignees=["@alice", "@bob"]
        )
        
        assert "@alice" in preview.assignees
        assert "@bob" in preview.assignees

    def test_preview_model_to_dict(self):
        """Test converting preview to dictionary."""
        preview = GitHubIssuePreview(
            repo="org/repo",
            title="Test Issue",
            body="Test body",
            labels=["ai-generated", "bug"]
        )
        
        result = preview.to_dict()
        
        assert result["repo"] == "org/repo"
        assert result["title"] == "Test Issue"
        assert "bug" in result["labels"]
