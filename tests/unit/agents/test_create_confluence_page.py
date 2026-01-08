"""
Unit tests for CreateConfluencePageAction handler (T157).

Tests the Confluence page creation action handler which generates previews and
executes page creation with space permission validation.
"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from src.agents.create_confluence_page import CreateConfluencePageAction, ConfluencePagePreview


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
def mock_confluence_client():
    """Mock Confluence API client."""
    client = AsyncMock()
    client.get_spaces = AsyncMock(return_value=[
        {"key": "DOCS", "name": "Documentation"},
        {"key": "TEAM", "name": "Team Space"}
    ])
    client.create_page = AsyncMock(return_value={
        "id": "12345",
        "title": "Q4 Planning Notes",
        "_links": {"webui": "/spaces/DOCS/pages/12345/Q4+Planning+Notes"}
    })
    client.check_create_permission = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_request():
    """Sample request for Confluence page creation."""
    return {
        "user_query": "Create documentation for Q4 planning",
        "context": {
            "space": "DOCS",
            "suggested_title": "Q4 Planning Notes",
            "suggested_body": "<h1>Q4 Goals</h1><p>Complete MVP launch...</p>"
        }
    }


class TestConfluencePagePreviewGeneration:
    """Test preview generation for Confluence page creation."""

    @pytest.mark.asyncio
    async def test_generate_preview_from_user_query(self, workspace_id, user_id, conversation_id, mock_confluence_client, sample_request):
        """Test generating preview from natural language query."""
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert isinstance(preview, ConfluencePagePreview)
        assert preview.space == "DOCS"
        assert "Q4 Planning" in preview.title
        assert "Q4 Goals" in preview.body

    @pytest.mark.asyncio
    async def test_preview_includes_ai_generated_label(self, workspace_id, user_id, conversation_id, mock_confluence_client, sample_request):
        """Test that preview automatically includes 'ai-generated' label."""
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        
        preview = await action.generate_preview(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            request=sample_request
        )
        
        assert "ai-generated" in preview.labels

    @pytest.mark.asyncio
    async def test_preview_validates_space_exists(self, workspace_id, user_id, conversation_id, mock_confluence_client):
        """Test that preview validation checks if space exists."""
        invalid_request = {
            "user_query": "Create page",
            "context": {"space": "INVALID"}
        }
        
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        
        with pytest.raises(ValueError, match="Space.*not found"):
            await action.generate_preview(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conversation_id,
                request=invalid_request
            )


class TestConfluencePageExecution:
    """Test execution of Confluence page creation."""

    @pytest.mark.asyncio
    async def test_execute_creates_confluence_page(self, workspace_id, user_id, mock_confluence_client):
        """Test that execute() creates actual Confluence page."""
        preview = ConfluencePagePreview(
            space="DOCS",
            title="Q4 Planning Notes",
            body="<h1>Q4 Goals</h1><p>Complete MVP...</p>",
            labels=["ai-generated", "planning"]
        )
        
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is True
        assert result.page_id == "12345"
        assert "https://confluence.example.com" in result.page_url

    @pytest.mark.asyncio
    async def test_execute_handles_confluence_api_errors(self, workspace_id, user_id, mock_confluence_client):
        """Test that execute() handles Confluence API errors gracefully."""
        mock_confluence_client.create_page.side_effect = Exception("Confluence API error")
        
        preview = ConfluencePagePreview(
            space="DOCS",
            title="Test Page",
            body="<p>Test content</p>",
            labels=["ai-generated"]
        )
        
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        result = await action.execute(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert result.success is False
        assert "error" in result.error_message.lower()


class TestConfluencePermissionChecks:
    """Test space permission validation."""

    @pytest.mark.asyncio
    async def test_check_permissions_validates_create_access(self, workspace_id, user_id, mock_confluence_client):
        """Test that permission check validates user can create pages."""
        preview = ConfluencePagePreview(
            space="DOCS",
            title="Test Page",
            body="<p>Test</p>",
            labels=["ai-generated"]
        )
        
        action = CreateConfluencePageAction(confluence_client=mock_confluence_client)
        has_permission = await action.check_permissions(
            workspace_id=workspace_id,
            user_id=user_id,
            preview=preview
        )
        
        assert has_permission is True


class TestConfluencePagePreviewModel:
    """Test ConfluencePagePreview data model."""

    def test_preview_model_with_parent_page(self):
        """Test creating preview with parent page."""
        preview = ConfluencePagePreview(
            space="DOCS",
            title="Child Page",
            body="<p>Content</p>",
            parent_page_id="11111",
            labels=["ai-generated"]
        )
        
        assert preview.parent_page_id == "11111"

    def test_preview_model_to_dict(self):
        """Test converting preview to dictionary."""
        preview = ConfluencePagePreview(
            space="TEAM",
            title="Team Docs",
            body="<p>Team content</p>",
            labels=["ai-generated", "team"]
        )
        
        result = preview.to_dict()
        
        assert result["space"] == "TEAM"
        assert result["title"] == "Team Docs"
        assert "team" in result["labels"]
