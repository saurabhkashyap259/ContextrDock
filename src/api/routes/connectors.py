"""API routes for connector management."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.api.schemas.connector import (
    ConnectorCreate,
    ConnectorDetailResponse,
    ConnectorListResponse,
    ConnectorResponse,
    ConnectorUpdate,
    SyncRunListResponse,
    SyncRunResponse,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from src.database import get_db
from src.models.connector import Connector
from src.models.sync_run import SyncRun, SyncStatus
from src.workers.sync_task import run_connector_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


def get_workspace_id() -> int:
    """Get workspace ID from auth context.

    TODO: Replace with actual auth/workspace resolution
    For now, returns hardcoded workspace ID for development.
    """
    return 1


def encrypt_credentials(credentials: dict) -> bytes:
    """Encrypt connector credentials.

    Args:
        credentials: Credentials dictionary

    Returns:
        Encrypted credentials as bytes

    TODO: Implement proper encryption using Fernet
    """
    import json
    # Placeholder - should use Fernet encryption
    return json.dumps(credentials).encode()


def decrypt_credentials(encrypted: bytes) -> dict:
    """Decrypt connector credentials.

    Args:
        encrypted: Encrypted credentials bytes

    Returns:
        Decrypted credentials dictionary

    TODO: Implement proper decryption using Fernet
    """
    import json
    # Placeholder - should use Fernet decryption
    return json.loads(encrypted.decode())


@router.get("", response_model=ConnectorListResponse)
def list_connectors(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    connector_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> ConnectorListResponse:
    """List all connectors for workspace.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        connector_type: Filter by connector type
        is_active: Filter by active status
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        List of connectors with pagination
    """
    query = db.query(Connector).filter_by(workspace_id=workspace_id)

    # Apply filters
    if connector_type:
        query = query.filter_by(connector_type=connector_type)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    connectors = query.order_by(desc(Connector.created_at)).offset(offset).limit(page_size).all()

    return ConnectorListResponse(
        connectors=[ConnectorResponse.model_validate(c) for c in connectors],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
def create_connector(
    connector_data: ConnectorCreate,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> ConnectorResponse:
    """Create a new connector.

    Args:
        connector_data: Connector creation data
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        Created connector

    Raises:
        HTTPException: If connector creation fails
    """
    try:
        # Encrypt credentials
        encrypted_creds = encrypt_credentials(connector_data.credentials.model_dump())

        # Create connector
        connector = Connector(
            workspace_id=workspace_id,
            connector_type=connector_data.connector_type,
            display_name=connector_data.display_name,
            config=connector_data.config,
            credentials_encrypted=encrypted_creds,
            sync_schedule=connector_data.sync_schedule,
            is_active=connector_data.is_active,
        )

        db.add(connector)
        db.commit()
        db.refresh(connector)

        logger.info(
            f"Created connector {connector.id} ({connector.connector_type}) "
            f"for workspace {workspace_id}"
        )

        return ConnectorResponse.model_validate(connector)

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create connector: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create connector: {str(e)}",
        )


@router.get("/{connector_id}", response_model=ConnectorDetailResponse)
def get_connector(
    connector_id: int,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> ConnectorDetailResponse:
    """Get connector by ID with recent sync runs.

    Args:
        connector_id: Connector ID
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        Connector details with recent sync runs

    Raises:
        HTTPException: If connector not found
    """
    connector = (
        db.query(Connector)
        .filter_by(id=connector_id, workspace_id=workspace_id)
        .first()
    )

    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    # Get recent sync runs
    recent_runs = (
        db.query(SyncRun)
        .filter_by(connector_id=connector_id)
        .order_by(desc(SyncRun.started_at))
        .limit(10)
        .all()
    )

    response_data = ConnectorResponse.model_validate(connector).model_dump()
    response_data["recent_sync_runs"] = [
        SyncRunResponse.model_validate(run) for run in recent_runs
    ]

    return ConnectorDetailResponse(**response_data)


@router.patch("/{connector_id}", response_model=ConnectorResponse)
def update_connector(
    connector_id: int,
    connector_data: ConnectorUpdate,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> ConnectorResponse:
    """Update connector configuration.

    Args:
        connector_id: Connector ID
        connector_data: Connector update data
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        Updated connector

    Raises:
        HTTPException: If connector not found or update fails
    """
    connector = (
        db.query(Connector)
        .filter_by(id=connector_id, workspace_id=workspace_id)
        .first()
    )

    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    try:
        # Update fields
        if connector_data.display_name is not None:
            connector.display_name = connector_data.display_name
        if connector_data.config is not None:
            connector.config = connector_data.config
        if connector_data.credentials is not None:
            encrypted_creds = encrypt_credentials(
                connector_data.credentials.model_dump()
            )
            connector.credentials_encrypted = encrypted_creds
        if connector_data.sync_schedule is not None:
            connector.sync_schedule = connector_data.sync_schedule
        if connector_data.is_active is not None:
            connector.is_active = connector_data.is_active

        db.commit()
        db.refresh(connector)

        logger.info(f"Updated connector {connector_id}")

        return ConnectorResponse.model_validate(connector)

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update connector {connector_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update connector: {str(e)}",
        )


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(
    connector_id: int,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete connector.

    Args:
        connector_id: Connector ID
        workspace_id: Workspace ID from auth
        db: Database session

    Raises:
        HTTPException: If connector not found or delete fails
    """
    connector = (
        db.query(Connector)
        .filter_by(id=connector_id, workspace_id=workspace_id)
        .first()
    )

    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    try:
        db.delete(connector)
        db.commit()

        logger.info(f"Deleted connector {connector_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete connector {connector_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete connector: {str(e)}",
        )


@router.post("/{connector_id}/sync", response_model=SyncTriggerResponse)
def trigger_sync(
    connector_id: int,
    sync_request: SyncTriggerRequest = SyncTriggerRequest(),
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> SyncTriggerResponse:
    """Trigger manual sync for connector.

    Args:
        connector_id: Connector ID
        sync_request: Sync trigger options
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        Sync trigger response with sync_run_id

    Raises:
        HTTPException: If connector not found or sync already running
    """
    connector = (
        db.query(Connector)
        .filter_by(id=connector_id, workspace_id=workspace_id)
        .first()
    )

    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    if not connector.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connector is not active",
        )

    # Check for running sync
    if not sync_request.force:
        running_sync = (
            db.query(SyncRun)
            .filter_by(connector_id=connector_id, status=SyncStatus.RUNNING.value)
            .first()
        )

        if running_sync:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sync already in progress. Use force=true to override.",
            )

    try:
        # Trigger sync task asynchronously
        result = run_connector_sync.delay(connector_id)

        logger.info(f"Triggered sync for connector {connector_id}, task_id={result.id}")

        # Get the sync run that was created
        sync_run = (
            db.query(SyncRun)
            .filter_by(connector_id=connector_id)
            .order_by(desc(SyncRun.started_at))
            .first()
        )

        return SyncTriggerResponse(
            sync_run_id=sync_run.id if sync_run else 0,
            status="queued",
            message=f"Sync task queued with task_id={result.id}",
        )

    except Exception as e:
        logger.error(f"Failed to trigger sync for connector {connector_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(e)}",
        )


@router.get("/{connector_id}/sync-runs", response_model=SyncRunListResponse)
def list_sync_runs(
    connector_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> SyncRunListResponse:
    """List sync runs for connector.

    Args:
        connector_id: Connector ID
        page: Page number (1-indexed)
        page_size: Number of items per page
        status_filter: Filter by sync status
        workspace_id: Workspace ID from auth
        db: Database session

    Returns:
        List of sync runs with pagination

    Raises:
        HTTPException: If connector not found
    """
    # Verify connector exists and belongs to workspace
    connector = (
        db.query(Connector)
        .filter_by(id=connector_id, workspace_id=workspace_id)
        .first()
    )

    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    query = db.query(SyncRun).filter_by(connector_id=connector_id)

    # Apply status filter
    if status_filter:
        query = query.filter_by(status=status_filter)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    sync_runs = (
        query.order_by(desc(SyncRun.started_at)).offset(offset).limit(page_size).all()
    )

    return SyncRunListResponse(
        sync_runs=[SyncRunResponse.model_validate(run) for run in sync_runs],
        total=total,
        page=page,
        page_size=page_size,
    )
