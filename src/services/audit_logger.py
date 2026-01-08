"""
Audit logging service (T173).

Centralizes creation of audit log entries for all write operations.
Ensures consistent logging format and simplifies audit trail management.
"""
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum

from sqlalchemy.orm import Session
from src.models.audit_log import AuditLog


logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Standard audit event types."""
    
    # Action events
    ACTION_CREATED = "action.created"
    ACTION_APPROVED = "action.approved"
    ACTION_EXECUTED = "action.executed"
    ACTION_FAILED = "action.failed"
    ACTION_CANCELLED = "action.cancelled"
    ACTION_EXPIRED = "action.expired"
    
    # Connector events
    CONNECTOR_CREATED = "connector.created"
    CONNECTOR_UPDATED = "connector.updated"
    CONNECTOR_DELETED = "connector.deleted"
    
    # Sync events
    SYNC_STARTED = "sync.started"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"
    
    # User events
    USER_INVITED = "user.invited"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_REMOVED = "user.removed"


class AuditLogger:
    """
    Service for creating audit log entries.
    
    Provides high-level methods for logging common operations and
    ensures consistent audit trail format across the application.
    """
    
    def __init__(self, db: Session):
        """
        Initialize audit logger.
        
        Args:
            db: Database session for creating audit log entries
        """
        self.db = db
    
    def _create_log_entry(
        self,
        workspace_id: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        details: Dict[str, Any],
        actor_user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Create and persist an audit log entry.
        
        Args:
            workspace_id: Workspace where event occurred
            action: Event type in 'entity.verb' format
            target_type: Type of entity affected (e.g., 'AgentAction', 'Connector')
            target_id: ID of entity affected
            details: Additional event context (stored in JSONB)
            actor_user_id: User who performed action (None for system events)
            ip_address: IP address of user (None for system events)
        
        Returns:
            Created AuditLog instance
        
        Raises:
            Exception: If database commit fails
        """
        try:
            log_entry = AuditLog(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details_json=details,
                ip_address=ip_address
            )
            
            self.db.add(log_entry)
            self.db.commit()
            
            logger.info(
                f"Audit log created: {action} on {target_type}:{target_id} "
                f"by {'system' if actor_user_id is None else f'user:{actor_user_id}'}"
            )
            
            return log_entry
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            self.db.rollback()
            raise
    
    # Action audit methods
    
    def log_action_created(
        self,
        workspace_id: UUID,
        user_id: UUID,
        action_id: UUID,
        action_type: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log creation of a new action.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who created the action
            action_id: ID of created action
            action_type: Type of action (e.g., 'create_jira_ticket')
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.ACTION_CREATED.value,
            target_type="AgentAction",
            target_id=action_id,
            details={"action_type": action_type},
            ip_address=ip_address
        )
    
    def log_action_approved(
        self,
        workspace_id: UUID,
        user_id: UUID,
        action_id: UUID,
        details: Dict[str, Any],
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log approval of an action.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who approved the action
            action_id: ID of approved action
            details: Approval details (e.g., preview_edited, edited_fields)
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.ACTION_APPROVED.value,
            target_type="AgentAction",
            target_id=action_id,
            details=details,
            ip_address=ip_address
        )
    
    def log_action_executed(
        self,
        workspace_id: UUID,
        action_id: UUID,
        result_url: str,
        execution_duration_ms: Optional[int] = None
    ) -> AuditLog:
        """
        Log successful execution of an action (system event).
        
        Args:
            workspace_id: Workspace ID
            action_id: ID of executed action
            result_url: URL of created resource (e.g., Jira ticket)
            execution_duration_ms: Execution time in milliseconds
        
        Returns:
            Created audit log entry
        """
        details = {"result_url": result_url}
        if execution_duration_ms is not None:
            details["execution_duration_ms"] = execution_duration_ms
        
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,  # System event
            action=AuditEventType.ACTION_EXECUTED.value,
            target_type="AgentAction",
            target_id=action_id,
            details=details
        )
    
    def log_action_failed(
        self,
        workspace_id: UUID,
        action_id: UUID,
        error_message: str,
        error_type: Optional[str] = None
    ) -> AuditLog:
        """
        Log failed execution of an action (system event).
        
        Args:
            workspace_id: Workspace ID
            action_id: ID of failed action
            error_message: Error message describing failure
            error_type: Error category (e.g., 'APIError', 'PermissionError')
        
        Returns:
            Created audit log entry
        """
        details = {"error_message": error_message}
        if error_type:
            details["error_type"] = error_type
        
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,  # System event
            action=AuditEventType.ACTION_FAILED.value,
            target_type="AgentAction",
            target_id=action_id,
            details=details
        )
    
    def log_action_cancelled(
        self,
        workspace_id: UUID,
        user_id: UUID,
        action_id: UUID,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log cancellation of an action.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who cancelled the action
            action_id: ID of cancelled action
            reason: Reason for cancellation
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        details = {}
        if reason:
            details["reason"] = reason
        
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.ACTION_CANCELLED.value,
            target_type="AgentAction",
            target_id=action_id,
            details=details,
            ip_address=ip_address
        )
    
    def log_action_expired(
        self,
        workspace_id: UUID,
        action_id: UUID
    ) -> AuditLog:
        """
        Log automatic expiration of an action (system event).
        
        Args:
            workspace_id: Workspace ID
            action_id: ID of expired action
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,  # System event
            action=AuditEventType.ACTION_EXPIRED.value,
            target_type="AgentAction",
            target_id=action_id,
            details={}
        )
    
    # Connector audit methods
    
    def log_connector_created(
        self,
        workspace_id: UUID,
        user_id: UUID,
        connector_id: UUID,
        connector_type: str,
        connector_name: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log creation of a new connector.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who created the connector
            connector_id: ID of created connector
            connector_type: Type of connector (e.g., 'jira', 'confluence')
            connector_name: Display name of connector
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.CONNECTOR_CREATED.value,
            target_type="Connector",
            target_id=connector_id,
            details={
                "connector_type": connector_type,
                "connector_name": connector_name
            },
            ip_address=ip_address
        )
    
    def log_connector_updated(
        self,
        workspace_id: UUID,
        user_id: UUID,
        connector_id: UUID,
        before: Dict[str, Any],
        after: Dict[str, Any],
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log update of connector configuration.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who updated the connector
            connector_id: ID of updated connector
            before: Configuration before update
            after: Configuration after update
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.CONNECTOR_UPDATED.value,
            target_type="Connector",
            target_id=connector_id,
            details={"before": before, "after": after},
            ip_address=ip_address
        )
    
    def log_connector_deleted(
        self,
        workspace_id: UUID,
        user_id: UUID,
        connector_id: UUID,
        connector_type: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log deletion of a connector.
        
        Args:
            workspace_id: Workspace ID
            user_id: User who deleted the connector
            connector_id: ID of deleted connector
            connector_type: Type of deleted connector
            ip_address: User's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=user_id,
            action=AuditEventType.CONNECTOR_DELETED.value,
            target_type="Connector",
            target_id=connector_id,
            details={"connector_type": connector_type},
            ip_address=ip_address
        )
    
    # Sync audit methods
    
    def log_sync_completed(
        self,
        workspace_id: UUID,
        connector_id: UUID,
        documents_indexed: int,
        duration_seconds: int
    ) -> AuditLog:
        """
        Log successful completion of sync operation (system event).
        
        Args:
            workspace_id: Workspace ID
            connector_id: ID of connector that synced
            documents_indexed: Number of documents indexed
            duration_seconds: Sync duration in seconds
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,  # System event
            action=AuditEventType.SYNC_COMPLETED.value,
            target_type="Connector",
            target_id=connector_id,
            details={
                "documents_indexed": documents_indexed,
                "duration_seconds": duration_seconds
            }
        )
    
    def log_sync_failed(
        self,
        workspace_id: UUID,
        connector_id: UUID,
        error_message: str,
        documents_processed: int
    ) -> AuditLog:
        """
        Log failed sync operation (system event).
        
        Args:
            workspace_id: Workspace ID
            connector_id: ID of connector that failed to sync
            error_message: Error message describing failure
            documents_processed: Number of documents processed before failure
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=None,  # System event
            action=AuditEventType.SYNC_FAILED.value,
            target_type="Connector",
            target_id=connector_id,
            details={
                "error_message": error_message,
                "documents_processed": documents_processed
            }
        )
    
    # User audit methods
    
    def log_user_role_changed(
        self,
        workspace_id: UUID,
        actor_user_id: UUID,
        target_user_id: UUID,
        old_role: str,
        new_role: str,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """
        Log change of user role.
        
        Args:
            workspace_id: Workspace ID
            actor_user_id: User who changed the role
            target_user_id: User whose role was changed
            old_role: Previous role
            new_role: New role
            ip_address: Actor's IP address
        
        Returns:
            Created audit log entry
        """
        return self._create_log_entry(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=AuditEventType.USER_ROLE_CHANGED.value,
            target_type="User",
            target_id=target_user_id,
            details={"old_role": old_role, "new_role": new_role},
            ip_address=ip_address
        )
    
    # Query helper methods
    
    def get_logs_for_target(
        self,
        workspace_id: UUID,
        target_type: str,
        target_id: UUID
    ) -> List[AuditLog]:
        """
        Get all audit logs for a specific target entity.
        
        Args:
            workspace_id: Workspace ID
            target_type: Type of entity
            target_id: ID of entity
        
        Returns:
            List of audit logs, ordered by creation time descending
        """
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.workspace_id == workspace_id,
                AuditLog.target_type == target_type,
                AuditLog.target_id == target_id
            )
            .order_by(AuditLog.created_at.desc())
            .all()
        )
    
    def get_logs_by_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        limit: int = 50
    ) -> List[AuditLog]:
        """
        Get recent audit logs by a specific user.
        
        Args:
            workspace_id: Workspace ID
            user_id: User ID
            limit: Maximum number of logs to return
        
        Returns:
            List of audit logs, ordered by creation time descending
        """
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.workspace_id == workspace_id,
                AuditLog.actor_user_id == user_id
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_recent_logs(
        self,
        workspace_id: UUID,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get recent audit logs for a workspace.
        
        Args:
            workspace_id: Workspace ID
            limit: Maximum number of logs to return
        
        Returns:
            List of audit logs, ordered by creation time descending
        """
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.workspace_id == workspace_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
