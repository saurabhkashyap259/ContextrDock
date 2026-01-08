"""
CreateGitHubIssueAction handler (T160).

Generates previews and executes GitHub issue creation with repository permission
validation. Supports AI-powered field extraction from natural language queries.
"""
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class GitHubIssuePreview:
    """
    Preview of GitHub issue to be created.

    All fields are editable by user before approval.

    Attributes:
        repo: Repository full name (e.g., "org/repo")
        title: Issue title
        body: Issue body (markdown)
        labels: List of labels (always includes 'ai-generated')
        assignees: Optional list of assignee usernames
        milestone: Optional milestone number
    """
    repo: str
    title: str
    body: str
    labels: list[str] = field(default_factory=lambda: ["ai-generated"])
    assignees: list[str] = field(default_factory=list)
    milestone: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert preview to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'GitHubIssuePreview':
        """Create preview from dictionary."""
        return cls(**data)


@dataclass
class GitHubExecutionResult:
    """
    Result of GitHub issue creation execution.

    Attributes:
        success: Whether execution succeeded
        issue_number: Created issue number
        issue_url: URL to view issue
        error_message: Error details if execution failed
    """
    success: bool
    issue_number: Optional[int] = None
    issue_url: Optional[str] = None
    error_message: Optional[str] = None


class CreateGitHubIssueAction:
    """
    Action handler for creating GitHub issues.

    Workflow:
    1. User requests issue creation via natural language
    2. generate_preview() extracts fields and creates editable preview
    3. check_permissions() validates user has create access in repository
    4. User reviews/edits preview and approves
    5. execute() creates actual GitHub issue
    """

    def __init__(self, github_client):
        """
        Initialize GitHub issue creation handler.

        Args:
            github_client: Async GitHub API client
        """
        self.github_client = github_client

    async def generate_preview(
        self,
        workspace_id: UUID,
        user_id: UUID,
        conversation_id: Optional[UUID],
        request: dict[str, Any]
    ) -> GitHubIssuePreview:
        """
        Generate preview from user request.

        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            conversation_id: Optional conversation context
            request: Request data containing user_query and context

        Returns:
            GitHubIssuePreview with extracted fields

        Raises:
            ValueError: If repository not found or required fields missing
        """
        user_query = request.get("user_query", "")
        context = request.get("context", {})

        # Extract or default repository
        repo = context.get("repo")
        if not repo:
            raise ValueError("Repository must be specified in context")

        # Validate repository exists
        repositories = await self.github_client.get_repositories()
        repo_names = [r["full_name"] for r in repositories]
        if repo not in repo_names:
            raise ValueError(f"Repository '{repo}' not found. Available repos: {', '.join(repo_names)}")

        # Extract title
        title = context.get("suggested_title") or self._extract_title(user_query)

        # Extract or generate body
        body = context.get("suggested_body") or self._generate_body(user_query)

        # Get labels and ensure 'ai-generated' is included
        labels = context.get("labels", [])
        if "ai-generated" not in labels:
            labels.insert(0, "ai-generated")

        # Optional assignees and milestone
        assignees = context.get("assignees", [])
        milestone = context.get("milestone")

        preview = GitHubIssuePreview(
            repo=repo,
            title=title,
            body=body,
            labels=labels,
            assignees=assignees,
            milestone=milestone
        )

        logger.info(f"Generated GitHub issue preview for user {user_id}: {repo}#{title}")

        return preview

    async def check_permissions(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: GitHubIssuePreview
    ) -> bool:
        """
        Check if user has permission to create issue in repository.

        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            preview: Preview of issue to create

        Returns:
            True if user has permission
        """
        try:
            has_permission = await self.github_client.check_create_permission(
                repo=preview.repo,
                user_id=str(user_id)
            )

            if not has_permission:
                logger.warning(f"User {user_id} lacks permission to create issues in repo {preview.repo}")

            return has_permission

        except Exception as e:
            logger.error(f"Error checking GitHub permissions: {e}")
            return False

    async def execute(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: GitHubIssuePreview
    ) -> GitHubExecutionResult:
        """
        Execute GitHub issue creation.

        Args:
            workspace_id: Workspace ID
            user_id: User who approved action
            preview: Approved preview with final field values

        Returns:
            GitHubExecutionResult with issue number/URL or error
        """
        try:
            response = await self.github_client.create_issue(
                repo=preview.repo,
                title=preview.title,
                body=preview.body,
                labels=preview.labels,
                assignees=preview.assignees,
                milestone=preview.milestone
            )

            issue_number = response["number"]
            issue_url = response["html_url"]

            logger.info(f"Successfully created GitHub issue #{issue_number} for user {user_id}")

            return GitHubExecutionResult(
                success=True,
                issue_number=issue_number,
                issue_url=issue_url
            )

        except Exception as e:
            error_msg = f"Failed to create GitHub issue: {str(e)}"
            logger.error(error_msg)

            return GitHubExecutionResult(
                success=False,
                error_message=error_msg
            )

    def _extract_title(self, query: str) -> str:
        """Extract title from query."""
        # Simple extraction - in production could use AI
        title = query.replace("Create issue to", "").strip()
        title = title.replace("Create issue for", "").strip()
        return title[:255] if title else "New Issue"

    def _generate_body(self, query: str) -> str:
        """Generate body content from query."""
        # For MVP, create simple markdown body
        # In production, could invoke AI to generate structured content
        return f"AI-generated issue from request:\n\n{query}\n\nPlease review and edit as needed."
