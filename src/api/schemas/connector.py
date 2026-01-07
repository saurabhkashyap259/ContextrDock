"""Pydantic schemas for Connector API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ConnectorConfigBase(BaseModel):
    """Base configuration for connectors."""

    pass


class ConnectorCredentials(BaseModel):
    """Connector OAuth credentials."""

    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scope: Optional[str] = None


class ConnectorCreate(BaseModel):
    """Schema for creating a connector."""

    connector_type: str = Field(..., description="Type of connector (slack, jira, etc.)")
    display_name: str = Field(..., min_length=1, max_length=255)
    config: Dict[str, Any] = Field(default_factory=dict, description="Connector configuration")
    credentials: ConnectorCredentials = Field(..., description="OAuth credentials")
    sync_schedule: Optional[str] = Field(
        None,
        description="Cron expression for sync schedule (e.g., '0 */6 * * *')",
    )
    is_active: bool = Field(default=True, description="Whether connector is active")

    @field_validator("connector_type")
    @classmethod
    def validate_connector_type(cls, v: str) -> str:
        """Validate connector type is supported."""
        allowed = ["slack", "jira", "confluence", "github", "figma", "dropbox"]
        if v not in allowed:
            raise ValueError(f"Connector type must be one of: {', '.join(allowed)}")
        return v

    @field_validator("sync_schedule")
    @classmethod
    def validate_cron_schedule(cls, v: Optional[str]) -> Optional[str]:
        """Validate cron expression format."""
        if v is None:
            return v

        parts = v.split()
        if len(parts) != 5:
            raise ValueError(
                "Cron expression must have 5 parts: minute hour day month weekday"
            )
        return v


class ConnectorUpdate(BaseModel):
    """Schema for updating a connector."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=255)
    config: Optional[Dict[str, Any]] = None
    credentials: Optional[ConnectorCredentials] = None
    sync_schedule: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("sync_schedule")
    @classmethod
    def validate_cron_schedule(cls, v: Optional[str]) -> Optional[str]:
        """Validate cron expression format."""
        if v is None:
            return v

        parts = v.split()
        if len(parts) != 5:
            raise ValueError(
                "Cron expression must have 5 parts: minute hour day month weekday"
            )
        return v


class SyncRunResponse(BaseModel):
    """Schema for sync run response."""

    id: int
    connector_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    documents_added: int = 0
    documents_updated: int = 0
    documents_deleted: int = 0
    error_message: Optional[str] = None
    cursor_state: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ConnectorResponse(BaseModel):
    """Schema for connector response."""

    id: int
    workspace_id: int
    connector_type: str
    display_name: str
    config: Dict[str, Any]
    sync_schedule: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    
    # Don't expose credentials in responses
    # credentials field is intentionally omitted

    model_config = {"from_attributes": True}


class ConnectorDetailResponse(ConnectorResponse):
    """Schema for detailed connector response with sync runs."""

    recent_sync_runs: List[SyncRunResponse] = Field(default_factory=list)


class ConnectorListResponse(BaseModel):
    """Schema for list of connectors."""

    connectors: List[ConnectorResponse]
    total: int
    page: int = 1
    page_size: int = 50


class SyncRunListResponse(BaseModel):
    """Schema for list of sync runs."""

    sync_runs: List[SyncRunResponse]
    total: int
    page: int = 1
    page_size: int = 50


class SyncTriggerRequest(BaseModel):
    """Schema for triggering a manual sync."""

    force: bool = Field(
        default=False,
        description="Force sync even if one is already running",
    )


class SyncTriggerResponse(BaseModel):
    """Schema for sync trigger response."""

    sync_run_id: int
    status: str
    message: str
