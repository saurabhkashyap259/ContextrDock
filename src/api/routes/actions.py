"""
Action API endpoints (T164).

RESTful API for managing AI-powered content creation actions with approval workflow.
"""
import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session

from src.api.schemas.action import (
    ActionCreateRequest,
    ActionApproveRequest,
    ActionResponse,
    ActionExecutionResponse,
    ActionListResponse,
    ActionFilterParams,
    ErrorResponse
)
from src.models.agent_action import AgentAction, ActionType, ActionStatus
from src.services.audit_logger import AuditLogger
from src.agents.create_jira_ticket import CreateJiraTicketAction
from src.agents.create_confluence_page import CreateConfluencePageAction
from src.agents.create_github_issue import CreateGitHubIssueAction
from src.database import get_db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/actions", tags=["actions"])


def get_workspace_and_user(
    x_workspace_id: UUID = Header(...),
    x_user_id: UUID = Header(...)
) -> tuple[UUID, UUID]:
    """Extract workspace and user IDs from headers."""
    return x_workspace_id, x_user_id


def get_action_handler(action_type: str, connector_clients: dict):
    """
    Get appropriate action handler for action type.
    
    Args:
        action_type: Type of action (create_jira_ticket, create_confluence_page, create_github_issue)
        connector_clients: Dictionary of API clients for external services
    
    Returns:
        Action handler instance
    
    Raises:
        HTTPException: If action type is unsupported
    """
    handlers = {
        "create_jira_ticket": lambda: CreateJiraTicketAction(connector_clients.get("jira")),
        "create_confluence_page": lambda: CreateConfluencePageAction(connector_clients.get("confluence")),
        "create_github_issue": lambda: CreateGitHubIssueAction(connector_clients.get("github"))
    }
    
    if action_type not in handlers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported action type: {action_type}"
        )
    
    return handlers[action_type]()


@router.post("", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
async def create_action(
    request_body: ActionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(get_workspace_and_user)
):
    """
    Create a new action with preview (initiates approval workflow).
    
    Workflow:
    1. Validate action type and get appropriate handler
    2. Generate preview from user query and context
    3. Check permissions (dry-run validation)
    4. Create AgentAction with status=PENDING_APPROVAL
    5. Log action.created to audit trail
    6. Return action with preview for user review
    
    Args:
        request_body: Action creation request
        request: FastAPI request object (for IP address)
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers
    
    Returns:
        Created action with preview
    
    Raises:
        HTTPException 400: Unsupported action type
        HTTPException 403: Permission check failed
        HTTPException 500: Preview generation or permission check error
    """
    workspace_id, user_id = ids
    
    try:
        # Get connector clients (from dependency injection in production)
        # For now, this is placeholder - will be injected via DI container
        connector_clients = request.app.state.connector_clients if hasattr(request.app.state, 'connector_clients') else {}
        
        # Get action handler
        handler = get_action_handler(request_body.action_type, connector_clients)
        
        # Generate preview
        logger.info(f"Generating preview for action type: {request_body.action_type}")
        preview_json = await handler.generate_preview(
            user_query=request_body.user_query,
            context=request_body.context
        )
        
        # Check permissions (dry-run)
        logger.info(f"Checking permissions for action type: {request_body.action_type}")
        has_permission = await handler.check_permissions(workspace_id=workspace_id, user_id=user_id)
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )
        
        # Create action
        action = AgentAction(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=request_body.conversation_id,
            action_type=ActionType(request_body.action_type),
            status=ActionStatus.PENDING_APPROVAL,
            preview_json=preview_json,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        db.add(action)
        db.flush()  # Get action ID
        
        # Log to audit trail
        audit_logger = AuditLogger(db)
        ip_address = request.client.host if request.client else None
        audit_logger.log_action_created(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=action.id,
            action_type=request_body.action_type,
            ip_address=ip_address
        )
        
        db.commit()
        db.refresh(action)
        
        logger.info(f"Action created successfully: {action.id}")
        return ActionResponse.model_validate(action)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Failed to create action: {e}", exc_info=True)
        db.rollback()
        
        if "preview" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate preview: {str(e)}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create action: {str(e)}"
            )


@router.post("/{action_id}/approve", response_model=ActionExecutionResponse)
async def approve_action(
    action_id: UUID,
    request_body: ActionApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(get_workspace_and_user)
):
    """
    Approve and execute an action.
    
    Workflow:
    1. Load action and validate status (must be PENDING_APPROVAL and not expired)
    2. Apply edited_preview if provided
    3. Update status to APPROVED
    4. Log action.approved to audit trail
    5. Execute action via appropriate handler
    6. Update status to EXECUTED/FAILED
    7. Log action.executed or action.failed
    8. Return execution result
    
    Args:
        action_id: ID of action to approve
        request_body: Approval request (with optional edited_preview)
        request: FastAPI request object (for IP address)
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers
    
    Returns:
        Execution result with status and result_url
    
    Raises:
        HTTPException 404: Action not found
        HTTPException 400: Action cannot be approved (already approved, expired, etc.)
        HTTPException 500: Execution error
    """
    workspace_id, user_id = ids
    
    # Load action
    action = db.query(AgentAction).filter(
        AgentAction.id == action_id,
        AgentAction.workspace_id == workspace_id
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found"
        )
    
    # Validate can be approved
    if not action.can_be_approved():
        if action.is_expired():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action has expired"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action cannot be approved (current status: {action.status.value})"
            )
    
    try:
        # Apply edited preview if provided
        if request_body.edited_preview:
            logger.info(f"Applying edited preview to action {action_id}")
            action.preview_json = request_body.edited_preview
        
        # Approve action
        action.approve()
        db.flush()
        
        # Log approval
        audit_logger = AuditLogger(db)
        ip_address = request.client.host if request.client else None
        audit_logger.log_action_approved(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=action_id,
            details={
                "preview_edited": request_body.edited_preview is not None,
                "edited_fields": list(request_body.edited_preview.keys()) if request_body.edited_preview else []
            },
            ip_address=ip_address
        )
        
        db.commit()
        
        # Execute action
        logger.info(f"Executing action {action_id} of type {action.action_type.value}")
        
        connector_clients = request.app.state.connector_clients if hasattr(request.app.state, 'connector_clients') else {}
        handler = get_action_handler(action.action_type.value, connector_clients)
        
        start_time = datetime.utcnow()
        result = await handler.execute(preview=action.preview_json)
        execution_duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        if result.success:
            # Mark as executed
            action.execute(result_url=result.result_url)
            db.flush()
            
            # Log execution
            audit_logger.log_action_executed(
                workspace_id=workspace_id,
                action_id=action_id,
                result_url=result.result_url,
                execution_duration_ms=execution_duration_ms
            )
            
            db.commit()
            db.refresh(action)
            
            logger.info(f"Action {action_id} executed successfully")
            return ActionExecutionResponse.model_validate(action)
        else:
            # Mark as failed
            action.fail(error_message=result.error_message)
            db.flush()
            
            # Log failure
            audit_logger.log_action_failed(
                workspace_id=workspace_id,
                action_id=action_id,
                error_message=result.error_message,
                error_type="ExecutionError"
            )
            
            db.commit()
            db.refresh(action)
            
            logger.error(f"Action {action_id} execution failed: {result.error_message}")
            return ActionExecutionResponse.model_validate(action)
            
    except Exception as e:
        logger.error(f"Failed to approve/execute action {action_id}: {e}", exc_info=True)
        db.rollback()
        
        # Mark action as failed
        try:
            action.fail(error_message=str(e))
            audit_logger = AuditLogger(db)
            audit_logger.log_action_failed(
                workspace_id=workspace_id,
                action_id=action_id,
                error_message=str(e),
                error_type=type(e).__name__
            )
            db.commit()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute action: {str(e)}"
        )


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: UUID,
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(get_workspace_and_user)
):
    """
    Get details of a specific action.
    
    Args:
        action_id: ID of action to retrieve
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers
    
    Returns:
        Action details
    
    Raises:
        HTTPException 404: Action not found
    """
    workspace_id, user_id = ids
    
    action = db.query(AgentAction).filter(
        AgentAction.id == action_id,
        AgentAction.workspace_id == workspace_id
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found"
        )
    
    return ActionResponse.model_validate(action)


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_action(
    action_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(get_workspace_and_user)
):
    """
    Cancel a pending or approved action.
    
    Args:
        action_id: ID of action to cancel
        request: FastAPI request object (for IP address)
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers
    
    Raises:
        HTTPException 404: Action not found
        HTTPException 400: Action cannot be cancelled
    """
    workspace_id, user_id = ids
    
    action = db.query(AgentAction).filter(
        AgentAction.id == action_id,
        AgentAction.workspace_id == workspace_id
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found"
        )
    
    if not action.can_be_cancelled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action cannot be cancelled (current status: {action.status.value})"
        )
    
    try:
        action.cancel()
        db.flush()
        
        # Log cancellation
        audit_logger = AuditLogger(db)
        ip_address = request.client.host if request.client else None
        audit_logger.log_action_cancelled(
            workspace_id=workspace_id,
            user_id=user_id,
            action_id=action_id,
            ip_address=ip_address
        )
        
        db.commit()
        
        logger.info(f"Action {action_id} cancelled by user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to cancel action {action_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel action: {str(e)}"
        )


@router.get("", response_model=ActionListResponse)
async def list_actions(
    filters: ActionFilterParams = Depends(),
    db: Session = Depends(get_db),
    ids: tuple[UUID, UUID] = Depends(get_workspace_and_user)
):
    """
    List actions with optional filtering and pagination.
    
    Args:
        filters: Filter parameters (status, action_type, user_id, conversation_id, pagination)
        db: Database session
        ids: Tuple of (workspace_id, user_id) from headers
    
    Returns:
        Paginated list of actions
    """
    workspace_id, user_id = ids
    
    # Base query
    query = db.query(AgentAction).filter(AgentAction.workspace_id == workspace_id)
    
    # Apply filters
    if filters.status:
        query = query.filter(AgentAction.status == ActionStatus(filters.status))
    if filters.action_type:
        query = query.filter(AgentAction.action_type == ActionType(filters.action_type))
    if filters.user_id:
        query = query.filter(AgentAction.user_id == filters.user_id)
    if filters.conversation_id:
        query = query.filter(AgentAction.conversation_id == filters.conversation_id)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (filters.page - 1) * filters.page_size
    actions = query.order_by(AgentAction.created_at.desc()).offset(offset).limit(filters.page_size).all()
    
    return ActionListResponse(
        items=[ActionResponse.model_validate(action) for action in actions],
        total=total,
        page=filters.page,
        page_size=filters.page_size
    )
