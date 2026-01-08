"""
CreateJiraTicketAction handler (T156).

Generates previews and executes Jira ticket creation with dry-run permission
validation. Supports AI-powered field extraction from natural language queries.
"""
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class JiraTicketPreview:
    """
    Preview of Jira ticket to be created.
    
    All fields are editable by user before approval. After approval,
    these fields are used to create the actual Jira ticket.
    
    Attributes:
        project: Jira project key (e.g., "PROJ")
        issue_type: Issue type name (Task, Bug, Story, etc.)
        summary: Ticket title/summary
        description: Detailed description (supports Jira markdown)
        priority: Priority name (Highest, High, Medium, Low, Lowest)
        assignee: Optional assignee email
        labels: List of labels (always includes 'ai-generated')
        components: Optional list of component names
        custom_fields: Optional dict of custom field values
    """
    project: str
    issue_type: str
    summary: str
    description: str
    priority: str
    labels: List[str] = field(default_factory=lambda: ["ai-generated"])
    assignee: Optional[str] = None
    components: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert preview to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JiraTicketPreview':
        """Create preview from dictionary."""
        return cls(**data)


@dataclass
class JiraExecutionResult:
    """
    Result of Jira ticket creation execution.
    
    Attributes:
        success: Whether execution succeeded
        ticket_key: Created ticket key (e.g., "PROJ-123")
        ticket_url: URL to view ticket
        error_message: Error details if execution failed
    """
    success: bool
    ticket_key: Optional[str] = None
    ticket_url: Optional[str] = None
    error_message: Optional[str] = None


class CreateJiraTicketAction:
    """
    Action handler for creating Jira tickets.
    
    Workflow:
    1. User requests ticket creation via natural language
    2. generate_preview() extracts fields and creates editable preview
    3. check_permissions() validates user has create access (dry-run)
    4. User reviews/edits preview and approves
    5. execute() creates actual Jira ticket
    
    Supports:
    - Natural language field extraction
    - Priority detection from keywords (urgent, critical, etc.)
    - Project validation against available projects
    - Dry-run permission checks
    - Custom fields and components
    """
    
    # Priority keywords for extraction from user query
    PRIORITY_KEYWORDS = {
        "highest": ["critical", "urgent", "blocker", "p0"],
        "high": ["important", "high priority", "asap", "p1"],
        "medium": ["normal", "medium priority", "p2"],
        "low": ["minor", "low priority", "nice-to-have", "p3"]
    }
    
    # Issue type keywords for extraction from user query
    ISSUE_TYPE_KEYWORDS = {
        "Bug": ["bug", "issue", "error", "defect", "broken"],
        "Task": ["task", "todo", "implement", "create", "add"],
        "Story": ["story", "feature", "user story", "as a user"],
        "Epic": ["epic", "initiative", "project"]
    }
    
    def __init__(self, jira_client):
        """
        Initialize Jira ticket creation handler.
        
        Args:
            jira_client: Async Jira API client
        """
        self.jira_client = jira_client
    
    async def generate_preview(
        self,
        workspace_id: UUID,
        user_id: UUID,
        conversation_id: Optional[UUID],
        request: Dict[str, Any]
    ) -> JiraTicketPreview:
        """
        Generate preview from user request.
        
        Extracts fields from natural language query and context, validates
        project exists, and creates editable preview for user approval.
        
        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            conversation_id: Optional conversation context
            request: Request data containing:
                - user_query: Natural language request
                - context: Optional context hints (project, labels, etc.)
        
        Returns:
            JiraTicketPreview with extracted and default fields
            
        Raises:
            ValueError: If project not found or required fields missing
        """
        user_query = request.get("user_query", "")
        context = request.get("context", {})
        
        # Extract or default project
        project = context.get("project")
        if not project:
            # Could extract from query or use default project
            raise ValueError("Project must be specified in context")
        
        # Validate project exists
        projects = await self.jira_client.get_projects()
        project_keys = [p["key"] for p in projects]
        if project not in project_keys:
            raise ValueError(f"Project '{project}' not found. Available projects: {', '.join(project_keys)}")
        
        # Extract issue type from query or use default
        issue_type = context.get("issue_type") or self._extract_issue_type(user_query)
        
        # Extract summary from context or query
        summary = context.get("suggested_summary") or self._extract_summary(user_query)
        
        # Extract description from context or generate from query
        description = context.get("suggested_description") or self._generate_description(user_query)
        
        # Extract priority from query keywords or context
        priority = context.get("suggested_priority") or self._extract_priority(user_query)
        
        # Get labels from context and ensure 'ai-generated' is included
        labels = context.get("labels", [])
        if "ai-generated" not in labels:
            labels.insert(0, "ai-generated")
        
        # Optional fields from context
        assignee = context.get("assignee")
        components = context.get("components", [])
        custom_fields = context.get("custom_fields", {})
        
        preview = JiraTicketPreview(
            project=project,
            issue_type=issue_type,
            summary=summary,
            description=description,
            priority=priority,
            labels=labels,
            assignee=assignee,
            components=components,
            custom_fields=custom_fields
        )
        
        logger.info(
            f"Generated Jira ticket preview for user {user_id}: "
            f"{project}-{issue_type}: {summary}"
        )
        
        return preview
    
    async def check_permissions(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: JiraTicketPreview
    ) -> bool:
        """
        Check if user has permission to create ticket (dry-run).
        
        Validates user has CREATE_ISSUE permission for specified project
        and issue type without actually creating the ticket.
        
        Args:
            workspace_id: Workspace ID
            user_id: User requesting action
            preview: Preview of ticket to create
        
        Returns:
            True if user has permission, False otherwise
        """
        try:
            has_permission = await self.jira_client.check_create_permission(
                project=preview.project,
                issue_type=preview.issue_type,
                user_id=str(user_id)
            )
            
            if not has_permission:
                logger.warning(
                    f"User {user_id} lacks permission to create {preview.issue_type} "
                    f"in project {preview.project}"
                )
            
            return has_permission
            
        except Exception as e:
            logger.error(f"Error checking Jira permissions: {e}")
            return False
    
    async def execute(
        self,
        workspace_id: UUID,
        user_id: UUID,
        preview: JiraTicketPreview
    ) -> JiraExecutionResult:
        """
        Execute Jira ticket creation.
        
        Creates actual Jira ticket using fields from approved preview.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who approved action
            preview: Approved preview with final field values
        
        Returns:
            JiraExecutionResult with ticket key/URL or error details
        """
        try:
            # Create ticket via Jira API
            response = await self.jira_client.create_issue(
                project=preview.project,
                issue_type=preview.issue_type,
                summary=preview.summary,
                description=preview.description,
                priority=preview.priority,
                assignee=preview.assignee,
                labels=preview.labels,
                components=preview.components,
                custom_fields=preview.custom_fields
            )
            
            ticket_key = response["key"]
            ticket_url = f"https://jira.example.com/browse/{ticket_key}"
            
            logger.info(
                f"Successfully created Jira ticket {ticket_key} "
                f"for user {user_id} in workspace {workspace_id}"
            )
            
            return JiraExecutionResult(
                success=True,
                ticket_key=ticket_key,
                ticket_url=ticket_url
            )
            
        except Exception as e:
            error_msg = f"Failed to create Jira ticket: {str(e)}"
            logger.error(error_msg)
            
            return JiraExecutionResult(
                success=False,
                error_message=error_msg
            )
    
    def _extract_issue_type(self, query: str) -> str:
        """
        Extract issue type from query using keyword matching.
        
        Args:
            query: User query string
        
        Returns:
            Issue type name (defaults to "Task")
        """
        query_lower = query.lower()
        
        for issue_type, keywords in self.ISSUE_TYPE_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                return issue_type
        
        return "Task"  # Default
    
    def _extract_summary(self, query: str) -> str:
        """
        Extract summary/title from query.
        
        Removes command prefixes like "create", "add", etc. and
        extracts core action phrase.
        
        Args:
            query: User query string
        
        Returns:
            Extracted summary (capitalized)
        """
        # Remove common command prefixes
        summary = re.sub(r"^(create|add|implement|fix|build)\s+(a\s+)?(task|ticket|issue|bug|story)\s+(to\s+|for\s+)?", "", query, flags=re.IGNORECASE)
        
        # Take first sentence if multiple sentences
        summary = summary.split(".")[0].strip()
        
        # Capitalize first letter
        if summary:
            summary = summary[0].upper() + summary[1:]
        
        return summary or "New task"
    
    def _generate_description(self, query: str) -> str:
        """
        Generate description from query.
        
        For simple queries, uses query as description. For complex queries,
        could invoke AI to generate structured description.
        
        Args:
            query: User query string
        
        Returns:
            Generated description
        """
        # For MVP, use query as description
        # In production, could invoke AI to generate structured description
        return f"AI-generated task from request:\n\n{query}\n\nPlease review and edit as needed."
    
    def _extract_priority(self, query: str) -> str:
        """
        Extract priority from query using keyword matching.
        
        Args:
            query: User query string
        
        Returns:
            Priority name (defaults to "Medium")
        """
        query_lower = query.lower()
        
        for priority, keywords in self.PRIORITY_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                return priority.capitalize()
        
        return "Medium"  # Default
