"""Message model for storing conversation messages."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from src.models.base import Base


class Message(Base):
    """
    Message represents a single message in a conversation.
    
    Messages follow the OpenAI chat format:
    - role: "user" (question), "assistant" (answer), "system" (instructions)
    - content: The message text
    - citations_json: For assistant messages, includes grounded citations
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Message content
    role = Column(String(50), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    
    # Citations for grounded responses (only for assistant messages)
    # Example: {"citations": [{"document_id": 123, "chunk_id": 456, "title": "...", "url": "...", "snippet": "..."}]}
    citations_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, role='{self.role}')>"
