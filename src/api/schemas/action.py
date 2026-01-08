"""
Pydantic schemas for agent actions API (T171).

Defines request/response schemas for action creation, approval, and retrieval.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator

from src.models.agent_action import ActionStatus, ActionType

# Request Schemas

class ActionCreateRequest(BaseModel):
    """
    Request to create a new agent action.

    User provides natural language query and context hints for preview generation.

    Attributes:
        action_type: Type of action to create
        user_query: Natural language request
        context: Optional context hints (project, space, repo, etc.)
        conversation_id: Optional conversation context
    """
    action_type: ActionType
    user_query: str = Field(..., min_length=1, max_length=5000, description="Natural language request")
    context: dict[str, Any] = Field(default_factory=dict, description="Context hints for preview generation")
    conversation_id: Optional[UUID] = Field(None, description="Optional conversation context")

    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "create_jira_ticket",
                "user_query": "Create a task to implement feature X with high priority",
                "context": {
                    "project": "PROJ",
                    "suggested_summary": "Implement feature X",
                    "suggested_priority": "High"
                }
            }
        }


class ActionApproveRequest(BaseModel):
    """
    Request to approve an agent action.

    User can optionally edit preview fields before approval.

    Attributes:
        edited_preview: Optional edited preview JSON (if user modified fields)
    """
    edited_preview: Optional[dict[str, Any]] = Field(
        None,
        description="Optional edited preview (if null, uses original preview)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "edited_preview": {
                    "project": "PROJ",
                    "issue_type": "Task",
                    "summary": "Updated: Implement feature X with tests",
                    "priority": "Highest"
                }
            }
        }


# Response Schemas

class ActionPreviewResponse(BaseModel):
    """
    Preview of action to be created.

    Contains all editable fields that user can modify before approval.

    Attributes:
        preview_json: Preview data with all editable fields
        expires_at: When preview expires (if not approved)
    """
    preview_json: dict[str, Any] = Field(..., description="Editable preview fields")
    expires_at: datetime = Field(..., description="Preview expiration timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "preview_json": {
                    "project": "PROJ",
                    "issue_type": "Task",
                    "summary": "Implement feature X",
                    "description": "As a user, I want...",
                    "priority": "High",
                    "labels": ["ai-generated"]
                },
                "expires_at": "2026-01-09T10:00:00"
            }
        }


class ActionResponse(BaseModel):
    """
    Complete action details.

    Includes current status, preview, execution result, etc.

    Attributes:
        id: Action ID
        workspace_id: Workspace ID
        user_id: User who requested action
        conversation_id: Optional conversation context
        action_type: Type of action
        status: Current status
        preview_json: Preview data (editable before approval)
        expires_at: Expiration timestamp
        result_url: URL of created resource (if executed)
        error_message: Error details (if failed)
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    id: UUID
    workspace_id: UUID
    user_id: UUID
    conversation_id: Optional[UUID]
    action_type: ActionType
    status: ActionStatus
    preview_json: dict[str, Any]
    expires_at: datetime
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "workspace_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "789e0123-e45b-67c8-9def-0123456789ab",
                "conversation_id": "456e7890-1abc-2def-3456-789abcdef012",
                "action_type": "create_jira_ticket",
                "status": "pending_approval",
                "preview_json": {
                    "project": "PROJ",
                    "issue_type": "Task",
                    "summary": "Implement feature X",
                    "priority": "High"
                },
                "expires_at": "2026-01-09T10:00:00",
                "result_url": None,
                "error_message": None,
                "created_at": "2026-01-08T10:00:00",
                "updated_at": "2026-01-08T10:00:00"
            }
        }


class ActionExecutionResponse(BaseModel):
    """
    Result of action execution.

    Returned after approval triggers execution.

    Attributes:
        id: Action ID
        status: Updated status (EXECUTED or FAILED)
        result_url: URL of created resource (if successful)
        error_message: Error details (if failed)
    """
    id: UUID
    status: ActionStatus
    result_url: Optional[str] = None
    error_message: Optional[str] = None

    @validator('status')
    def validate_execution_status(cls, v):
        """Ensure status is EXECUTED or FAILED."""
        if v not in [ActionStatus.EXECUTED, ActionStatus.FAILED]:
            raise ValueError("Execution response must have EXECUTED or FAILED status")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "executed",
                "result_url": "https://jira.example.com/browse/PROJ-123",
                "error_message": None
            }
        }


class ActionListResponse(BaseModel):
    """
    Paginated list of actions.

    Attributes:
        items: List of actions
        total: Total count (for pagination)
        page: Current page
        page_size: Items per page
    """
    items: list[ActionResponse]
    total: int
    page: int
    page_size: int

    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 42,
                "page": 1,
                "page_size": 20
            }
        }


# Audit Log Schemas

class AuditLogResponse(BaseModel):
    """
    Audit log entry.

    Tracks all write operations for compliance.

    Attributes:
        id: Log entry ID
        workspace_id: Workspace ID
        actor_user_id: User who performed action (null for system)
        actor_type: 'user' or 'system'
        action: Action type (entity.verb format)
        target_type: Type of target entity
        target_id: ID of target entity
        details_json: Additional context (before/after, errors, etc.)
        ip_address: Client IP address
        created_at: Event timestamp
    """
    id: UUID
    workspace_id: UUID
    actor_user_id: Optional[UUID]
    actor_type: str
    action: str
    target_type: str
    target_id: UUID
    details_json: dict[str, Any]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "abc12345-def6-7890-abcd-ef1234567890",
                "workspace_id": "123e4567-e89b-12d3-a456-426614174000",
                "actor_user_id": "789e0123-e45b-67c8-9def-0123456789ab",
                "actor_type": "user",
                "action": "action.approved",
                "target_type": "AgentAction",
                "target_id": "550e8400-e29b-41d4-a716-446655440000",
                "details_json": {
                    "before": {"status": "pending_approval"},
                    "after": {"status": "approved"}
                },
                "ip_address": "192.168.1.100",
                "created_at": "2026-01-08T10:15:00"
            }
        }


class AuditLogListResponse(BaseModel):
    """
    Paginated list of audit logs.

    Attributes:
        items: List of audit log entries
        total: Total count (for pagination)
        page: Current page
        page_size: Items per page
    """
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int

    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 157,
                "page": 1,
                "page_size": 50
            }
        }


# Error Response Schema

class ErrorResponse(BaseModel):
    """
    Standard error response.

    Attributes:
        error: Error type
        message: Human-readable error message
        details: Optional additional error details
    """
    error: str
    message: str
    details: Optional[dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "error": "PermissionDenied",
                "message": "User lacks permission to create issues in project PROJ",
                "details": {
                    "project": "PROJ",
                    "required_permission": "CREATE_ISSUE"
                }
            }
        }


# Query Parameter Schemas

class ActionFilterParams(BaseModel):
    """
    Query parameters for filtering actions.

    Attributes:
        status: Filter by status
        action_type: Filter by action type
        user_id: Filter by user
        conversation_id: Filter by conversation
        page: Page number (1-indexed)
        page_size: Items per page
    """
    status: Optional[ActionStatus] = None
    action_type: Optional[ActionType] = None
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (1-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "pending_approval",
                "page": 1,
                "page_size": 20
            }
        }


class AuditLogFilterParams(BaseModel):
    """
    Query parameters for filtering audit logs.

    Attributes:
        action: Filter by action type
        target_type: Filter by target entity type
        target_id: Filter by target entity ID
        actor_user_id: Filter by actor user
        start_date: Filter logs after this date
        end_date: Filter logs before this date
        page: Page number (1-indexed)
        page_size: Items per page
    """
    action: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=200, description="Items per page (1-200)")

    class Config:
        json_schema_extra = {
            "example": {
                "action": "action.approved",
                "target_type": "AgentAction",
                "start_date": "2026-01-01T00:00:00",
                "page": 1,
                "page_size": 50
            }
        }
