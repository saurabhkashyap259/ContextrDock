"""User model for authentication and identity management."""

from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.base import Base


class User(Base):
    """User represents an individual with access to the platform.

    Users are scoped to a workspace and have identity mappings to
    various connectors for permission-aware retrieval.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False, default="user")

    # JSONB field storing connector-specific user IDs
    # Example: {"slack": "U123456", "jira": "account-id-123", "github": "username"}
    connector_identities = Column(JSONB, nullable=False, default=dict, server_default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    workspace: Any = relationship("Workspace", backref="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
