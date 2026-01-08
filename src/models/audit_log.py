"""
AuditLog model (T153).

Provides immutable audit trail for all write operations in the system.
Tracks who did what, when, and stores before/after state changes.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.database import Base


class AuditLog(Base):
    """
    Immutable audit log entry for compliance and debugging.

    Records all significant write operations:
    - Connector creation/update/deletion
    - Agent action approval/execution/cancellation
    - Sync run completion/failure
    - User role changes
    - Permission modifications

    Audit logs are INSERT-only (no UPDATE or DELETE) to ensure integrity
    of the audit trail. Retention policy keeps logs for minimum 1 year.

    Attributes:
        id: Unique log entry identifier
        workspace_id: Workspace where action occurred
        actor_user_id: User who performed action (NULL for system actions)
        action: Action type in format 'entity.verb' (e.g., 'action.approved')
        target_type: Type of entity affected (Connector, AgentAction, etc.)
        target_id: ID of affected entity
        details_json: Additional context (before/after state, error details, etc.)
        ip_address: Client IP address (NULL for system actions)
        created_at: Event timestamp (immutable)
    """
    __tablename__ = "audit_logs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)

    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=False)
    target_id = Column(PGUUID(as_uuid=True), nullable=False)

    details_json = Column(JSONB, nullable=False, default={})
    ip_address = Column(INET, nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow, index=True)

    # Composite index for entity history queries
    __table_args__ = (
        CheckConstraint("action ~ '^[a-z_]+\\.[a-z_]+$'", name="action_format_check"),
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="audit_logs")
    actor_user = relationship("User", back_populates="audit_logs", foreign_keys=[actor_user_id])

    def __init__(
        self,
        workspace_id: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        actor_user_id: Optional[UUID] = None,
        details_json: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize AuditLog.

        Args:
            workspace_id: Workspace where action occurred
            action: Action type in 'entity.verb' format
            target_type: Type of affected entity
            target_id: ID of affected entity
            actor_user_id: User who performed action (NULL for system)
            details_json: Additional context (before/after, errors, etc.)
            ip_address: Client IP address
        """
        super().__init__(**kwargs)
        self.workspace_id = workspace_id
        self.actor_user_id = actor_user_id
        self.action = action
        self.target_type = target_type
        self.target_id = target_id
        self.details_json = details_json if details_json is not None else {}
        self.ip_address = ip_address

    def is_system_action(self) -> bool:
        """
        Check if action was performed by system (vs user).

        Returns:
            True if actor_user_id is NULL (system action)
        """
        return self.actor_user_id is None

    def get_actor_type(self) -> str:
        """
        Get actor type as string.

        Returns:
            'system' if system action, 'user' if user action
        """
        return "system" if self.is_system_action() else "user"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert audit log to dictionary representation.

        Returns:
            Dictionary with all log fields
        """
        return {
            "id": str(self.id) if self.id else None,
            "workspace_id": str(self.workspace_id),
            "actor_user_id": str(self.actor_user_id) if self.actor_user_id else None,
            "actor_type": self.get_actor_type(),
            "action": self.action,
            "target_type": self.target_type,
            "target_id": str(self.target_id),
            "details_json": self.details_json,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        """String representation of AuditLog."""
        actor = self.actor_user_id if self.actor_user_id else "system"
        return (
            f"<AuditLog(id={self.id}, "
            f"action={self.action}, "
            f"actor={actor}, "
            f"target={self.target_type}:{self.target_id}, "
            f"created_at={self.created_at})>"
        )
