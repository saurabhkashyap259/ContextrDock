"""
CreateConfluencePageAction handler (T158).

Generates previews and executes Confluence page creation with space permission
validation. Supports AI-powered content generation from natural language queries.
"""
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class ConfluencePagePreview:
    """
    Preview of Confluence page to be created.

    All fields are editable by user before approval.

    Attributes:
        space: Confluence space key (e.g., "DOCS")
        title: Page title
        body: Page body content (HTML/storage format)
        parent_page_id: Optional parent page ID for hierarchy
        labels: List of labels (always includes 'ai-generated')
    """
    space: str
    title: str
    body: str
    labels: list[str] = field(default_factory=lambda: ["ai-generated"])
    parent_page_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert preview to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ConfluencePagePreview':
        """Create preview from dictionary."""
        return cls(**data)


@dataclass
class ConfluenceExecutionResult:
    """
    Result of Confluence page creation execution.

    Attributes:
        success: Whether execution succeeded
        page_id: Created page ID
        page_url: URL to view page
        error_message: Error details if execution failed
    """
    success: bool
    page_id: Optional[str] = None
    page_url: Optional[str] = None
    error_message: Optional[str] = None


class CreateConfluencePageAction:
    """
    Action handler for creating Confluence pages.

    Workflow:
    1. User requests page creation via natural language
    2. generate_preview() extracts fields and creates editable preview
    3. check_permissions() validates user has create access in space
    4. User reviews/edits preview and approves
    5. execute() creates actual Confluence page
    """

    def __init__(self, confluence_client):
        """
        Initialize Confluence page creation handler.

        Args:
            confluence_client: Async Confluence API client
        """
        self.confluence_client = confluence_client

    async def generate_preview(
        self,
        workspace_id: UUID,
        user_id: UUID,
        conversation_id: Optional[UUID],
        request: dict[str, Any]
    ) -> ConfluencePagePreview:
        """
        Generate preview from user request.

        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            conversation_id: Optional conversation context
            request: Request data containing user_query and context

        Returns:
            ConfluencePagePreview with extracted fields

        Raises:
            ValueError: If space not found or required fields missing
        """
        user_query = request.get("user_query", "")
        context = request.get("context", {})

        # Extract or default space
        space = context.get("space")
        if not space:
            raise ValueError("Space must be specified in context")

        # Validate space exists
        spaces = await self.confluence_client.get_spaces()
        space_keys = [s["key"] for s in spaces]
        if space not in space_keys:
            raise ValueError(f"Space '{space}' not found. Available spaces: {', '.join(space_keys)}")

        # Extract title
        title = context.get("suggested_title") or self._extract_title(user_query)

        # Extract or generate body
        body = context.get("suggested_body") or self._generate_body(user_query)

        # Get labels and ensure 'ai-generated' is included
        labels = context.get("labels", [])
        if "ai-generated" not in labels:
            labels.insert(0, "ai-generated")

        # Optional parent page
        parent_page_id = context.get("parent_page_id")

        preview = ConfluencePagePreview(
            space=space,
            title=title,
            body=body,
            labels=labels,
            parent_page_id=parent_page_id
        )

        logger.info(f"Generated Confluence page preview for user {user_id}: {space}/{title}")

        return preview

    async def check_permissions(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: ConfluencePagePreview
    ) -> bool:
        """
        Check if user has permission to create page in space.

        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            preview: Preview of page to create

        Returns:
            True if user has permission
        """
        try:
            has_permission = await self.confluence_client.check_create_permission(
                space=preview.space,
                user_id=str(user_id)
            )

            if not has_permission:
                logger.warning(f"User {user_id} lacks permission to create pages in space {preview.space}")

            return has_permission

        except Exception as e:
            logger.error(f"Error checking Confluence permissions: {e}")
            return False

    async def execute(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: ConfluencePagePreview
    ) -> ConfluenceExecutionResult:
        """
        Execute Confluence page creation.

        Args:
            workspace_id: Workspace ID
            user_id: User who approved action
            preview: Approved preview with final field values

        Returns:
            ConfluenceExecutionResult with page ID/URL or error
        """
        try:
            response = await self.confluence_client.create_page(
                space=preview.space,
                title=preview.title,
                body=preview.body,
                parent_page_id=preview.parent_page_id,
                labels=preview.labels
            )

            page_id = response["id"]
            page_url = f"https://confluence.example.com{response['_links']['webui']}"

            logger.info(f"Successfully created Confluence page {page_id} for user {user_id}")

            return ConfluenceExecutionResult(
                success=True,
                page_id=page_id,
                page_url=page_url
            )

        except Exception as e:
            error_msg = f"Failed to create Confluence page: {str(e)}"
            logger.error(error_msg)

            return ConfluenceExecutionResult(
                success=False,
                error_message=error_msg
            )

    def _extract_title(self, query: str) -> str:
        """Extract title from query."""
        # Simple extraction - in production could use AI
        title = query.replace("Create documentation for", "").strip()
        title = title.replace("Create page for", "").strip()
        return title[:255] if title else "New Page"

    def _generate_body(self, query: str) -> str:
        """Generate body content from query."""
        # For MVP, create simple HTML body
        # In production, could invoke AI to generate structured content
        return f"<p>AI-generated page from request:</p><p>{query}</p><p>Please review and edit as needed.</p>"
