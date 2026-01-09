"""
AgentAction model (T151).

Tracks AI-generated content creation requests that require human approval.
Supports Jira ticket, Confluence page, and GitHub issue creation with preview
generation and approval workflow.
"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.database import Base


class ActionType(str, Enum):
    """Enumeration of supported action types."""
    CREATE_JIRA_TICKET = "create_jira_ticket"
    CREATE_CONFLUENCE_PAGE = "create_confluence_page"
    CREATE_GITHUB_ISSUE = "create_github_issue"


class ActionStatus(str, Enum):
    """Enumeration of action lifecycle statuses."""
    PENDING_APPROVAL = "pending_approval"  # Awaiting user approval
    APPROVED = "approved"                  # User approved, ready for execution
    EXECUTED = "executed"                  # Successfully executed
    CANCELLED = "cancelled"                # User cancelled before execution
    EXPIRED = "expired"                    # Expired before approval
    FAILED = "failed"                      # Execution failed


class AgentAction(Base):
    """
    Represents an AI-generated action requiring human approval.

    Workflow:
    1. User requests content creation via chat/API
    2. System generates preview with all fields populated
    3. Action created with status=PENDING_APPROVAL
    4. User reviews preview, optionally edits fields
    5. User approves → status=APPROVED → execution → status=EXECUTED
    6. Or user cancels → status=CANCELLED
    7. Or expires after 24 hours → status=EXPIRED

    Attributes:
        id: Unique action identifier
        workspace_id: Workspace containing this action
        user_id: User who requested the action
        conversation_id: Optional conversation context
        action_type: Type of action (Jira, Confluence, GitHub)
        status: Current lifecycle status
        preview_json: Action details (editable before approval)
        expires_at: Expiration timestamp (24 hours default)
        result_url: URL of created resource (set after execution)
        error_message: Error details if execution failed
        created_at: Action creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "agent_actions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)

    action_type = Column(SQLEnum(ActionType, name="action_type"), nullable=False)
    status = Column(SQLEnum(ActionStatus, name="action_status"), nullable=False, default=ActionStatus.PENDING_APPROVAL)

    preview_json = Column(JSONB, nullable=False, default={})
    expires_at = Column(DateTime(timezone=False), nullable=False)

    result_url = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workspace = relationship("Workspace", back_populates="agent_actions")
    user = relationship("User", back_populates="agent_actions")
    conversation = relationship("Conversation", back_populates="agent_actions")

    def __init__(
        self,
        workspace_id: int,
        user_id: int,
        action_type: ActionType,
        preview_json: dict[str, Any],
        conversation_id: Optional[int] = None,
        status: ActionStatus = ActionStatus.PENDING_APPROVAL,
        expires_at: Optional[datetime] = None,
        result_url: Optional[str] = None,
        error_message: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize AgentAction.

        Args:
            workspace_id: Workspace containing this action
            user_id: User who requested the action
            action_type: Type of action to perform
            preview_json: Action details (editable fields)
            conversation_id: Optional conversation context
            status: Initial status (default: PENDING_APPROVAL)
            expires_at: Expiration timestamp (default: now + 24 hours)
            result_url: URL of created resource (set after execution)
            error_message: Error details if execution failed
        """
        super().__init__(**kwargs)
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.action_type = action_type
        self.status = status
        self.preview_json = preview_json if preview_json is not None else {}
        self.expires_at = expires_at if expires_at is not None else (datetime.utcnow() + timedelta(hours=24))
        self.result_url = result_url
        self.error_message = error_message

    def is_expired(self) -> bool:
        """
        Check if action has expired.

        Returns:
            True if current time is past expires_at
        """
        return datetime.utcnow() > self.expires_at

    def mark_as_expired(self) -> None:
        """Mark action as expired."""
        self.status = ActionStatus.EXPIRED

    def can_be_approved(self) -> bool:
        """
        Check if action can be approved.

        Returns:
            True if status is PENDING_APPROVAL and not expired
        """
        return (
            self.status == ActionStatus.PENDING_APPROVAL
            and not self.is_expired()
        )

    def can_be_cancelled(self) -> bool:
        """
        Check if action can be cancelled.

        Returns:
            True if status is PENDING_APPROVAL or APPROVED (not yet executed)
        """
        return self.status in [ActionStatus.PENDING_APPROVAL, ActionStatus.APPROVED]

    def approve(self) -> None:
        """
        Approve the action for execution.

        Raises:
            ValueError: If action cannot be approved
        """
        if not self.can_be_approved():
            raise ValueError(
                f"Action cannot be approved: status={self.status.value}, "
                f"expired={self.is_expired()}"
            )
        self.status = ActionStatus.APPROVED

    def execute(self, result_url: str) -> None:
        """
        Mark action as successfully executed.

        Args:
            result_url: URL of created resource

        Raises:
            ValueError: If action is not approved
        """
        if self.status != ActionStatus.APPROVED:
            raise ValueError(f"Action must be approved before execution: status={self.status.value}")

        self.status = ActionStatus.EXECUTED
        self.result_url = result_url

    def fail(self, error_message: str) -> None:
        """
        Mark action as failed.

        Args:
            error_message: Error details
        """
        self.status = ActionStatus.FAILED
        self.error_message = error_message

    def cancel(self) -> None:
        """
        Cancel the action.

        Raises:
            ValueError: If action cannot be cancelled
        """
        if not self.can_be_cancelled():
            raise ValueError(f"Action cannot be cancelled: status={self.status.value}")

        self.status = ActionStatus.CANCELLED

    def to_dict(self) -> dict[str, Any]:
        """
        Convert action to dictionary representation.

        Returns:
            Dictionary with all action fields
        """
        return {
            "id": str(self.id) if self.id else None,
            "workspace_id": str(self.workspace_id),
            "user_id": str(self.user_id),
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "preview_json": self.preview_json,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "result_url": self.result_url,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        """String representation of AgentAction."""
        return (
            f"<AgentAction(id={self.id}, "
            f"type={self.action_type.value}, "
            f"status={self.status.value}, "
            f"expires_at={self.expires_at})>"
        )
