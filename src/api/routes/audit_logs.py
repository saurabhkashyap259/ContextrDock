"""
Admin audit log API endpoints (T175).

Admin-only endpoints for retrieving audit logs with filtering and pagination.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.action import (
    AuditLogFilterParams,
    AuditLogListResponse,
    AuditLogResponse,
)
from src.database import get_db
from src.models.audit_log import AuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/audit-logs", tags=["admin", "audit"])


def require_admin_role(
    x_workspace_id: UUID = Header(...),
    x_user_id: UUID = Header(...),
    x_user_role: str = Header(...)
) -> tuple[UUID, UUID]:
    """
    Require admin role for accessing audit logs.

    Args:
        x_workspace_id: Workspace ID from header
        x_user_id: User ID from header
        x_user_role: User role from header

    Returns:
        Tuple of (workspace_id, user_id)

    Raises:
        HTTPException 401: Missing role header
        HTTPException 403: User is not an admin
    """
    if not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User role not provided"
        )

    if x_user_role.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to access audit logs"
        )

    return x_workspace_id, x_user_id


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    filters: AuditLogFilterParams = Depends(),
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(require_admin_role)
):
    """
    Retrieve audit logs with optional filtering and pagination (admin only).

    Audit logs provide a complete, immutable record of all write operations
    in the workspace for compliance and security auditing.

    Filter options:
    - action: Filter by action type (e.g., 'action.approved', 'connector.created')
    - target_type: Filter by entity type (e.g., 'AgentAction', 'Connector')
    - target_id: Filter by specific entity ID
    - actor_user_id: Filter by user who performed action
    - start_date: Filter by logs created after this date
    - end_date: Filter by logs created before this date
    - page: Page number (1-indexed, default: 1)
    - page_size: Items per page (1-200, default: 50)

    Args:
        filters: Filter and pagination parameters
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers

    Returns:
        Paginated list of audit logs, ordered by creation time descending (newest first)

    Raises:
        HTTPException 401: Missing role header
        HTTPException 403: User is not an admin
        HTTPException 422: Invalid filter parameters
    """
    workspace_id, user_id = ids

    try:
        # Base query - all logs for workspace
        query = db.query(AuditLog).filter(AuditLog.workspace_id == workspace_id)

        # Apply filters
        if filters.action:
            query = query.filter(AuditLog.action == filters.action)

        if filters.target_type:
            query = query.filter(AuditLog.target_type == filters.target_type)

        if filters.target_id:
            query = query.filter(AuditLog.target_id == filters.target_id)

        if filters.actor_user_id:
            query = query.filter(AuditLog.actor_user_id == filters.actor_user_id)

        if filters.start_date:
            query = query.filter(AuditLog.created_at >= filters.start_date)

        if filters.end_date:
            query = query.filter(AuditLog.created_at <= filters.end_date)

        # Get total count before pagination
        total = query.count()

        # Apply pagination and ordering
        offset = (filters.page - 1) * filters.page_size
        logs = (
            query
            .order_by(AuditLog.created_at.desc())  # Newest first
            .offset(offset)
            .limit(filters.page_size)
            .all()
        )

        logger.info(
            f"Retrieved {len(logs)} audit logs (page {filters.page}, "
            f"total {total}) for workspace {workspace_id} by admin {user_id}"
        )

        return AuditLogListResponse(
            items=[AuditLogResponse.model_validate(log) for log in logs],
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit logs: {str(e)}"
        )
