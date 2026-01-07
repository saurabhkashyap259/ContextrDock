"""Conversation model for tracking query sessions."""

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class Conversation(Base):
    """
    Conversation represents a query session between a user and the system.
    
    Conversations can occur in multiple channels:
    - Web UI: Direct user interaction
    - Slack: Bot conversations in Slack channels
    - API: Programmatic interactions
    
    Each conversation contains multiple messages (queries and responses).
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Channel information
    channel_type = Column(String(50), nullable=False)  # "web", "slack", "api"
    external_channel_id = Column(String(255), nullable=True, index=True)  # Slack channel ID, etc.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id={self.user_id}, channel_type='{self.channel_type}')>"
