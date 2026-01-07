"""Pydantic schemas for query API endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Citation for a grounded answer."""
    
    chunk_id: int = Field(..., description="ID of the document chunk")
    document_id: int = Field(..., description="ID of the source document")
    title: Optional[str] = Field(None, description="Document title")
    url: Optional[str] = Field(None, description="Deep link to source")
    score: float = Field(..., description="Relevance score (0-1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": 123,
                "document_id": 45,
                "title": "API Authentication Guide",
                "url": "https://confluence.example.com/pages/12345",
                "score": 0.92,
            }
        }


class QueryRequest(BaseModel):
    """Request to query knowledge base."""
    
    question: str = Field(..., min_length=1, max_length=2000, description="Natural language question")
    conversation_id: Optional[int] = Field(None, description="ID of conversation to continue")
    max_results: int = Field(10, ge=1, le=50, description="Maximum citations to return")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="LLM sampling temperature")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is our OAuth 2.0 implementation?",
                "conversation_id": None,
                "max_results": 10,
                "temperature": 0.7,
            }
        }


class QueryResponse(BaseModel):
    """Response from knowledge base query."""
    
    answer: str = Field(..., description="Generated answer with grounded information")
    citations: List[Citation] = Field(default_factory=list, description="Sources used to generate answer")
    conversation_id: int = Field(..., description="ID of conversation (for follow-ups)")
    message_id: int = Field(..., description="ID of this message")
    usage: Dict[str, int] = Field(..., description="Token usage statistics")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Our OAuth 2.0 implementation follows the Authorization Code flow...",
                "citations": [
                    {
                        "chunk_id": 123,
                        "document_id": 45,
                        "title": "API Authentication Guide",
                        "url": "https://confluence.example.com/pages/12345",
                        "score": 0.92,
                    }
                ],
                "conversation_id": 1,
                "message_id": 2,
                "usage": {"prompt_tokens": 1250, "completion_tokens": 180, "total_tokens": 1430},
            }
        }


class Message(BaseModel):
    """Message in a conversation."""
    
    id: int = Field(..., description="Message ID")
    conversation_id: int = Field(..., description="Conversation ID")
    role: str = Field(..., description="Message role: user, assistant, system")
    content: str = Field(..., description="Message content")
    citations: Optional[List[Citation]] = Field(None, description="Citations (for assistant messages)")
    created_at: datetime = Field(..., description="Message creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 2,
                "conversation_id": 1,
                "role": "assistant",
                "content": "Our OAuth 2.0 implementation follows the Authorization Code flow...",
                "citations": [
                    {
                        "chunk_id": 123,
                        "document_id": 45,
                        "title": "API Authentication Guide",
                        "url": "https://confluence.example.com/pages/12345",
                        "score": 0.92,
                    }
                ],
                "created_at": "2024-01-15T10:30:00Z",
            }
        }


class Conversation(BaseModel):
    """Conversation metadata."""
    
    id: int = Field(..., description="Conversation ID")
    workspace_id: int = Field(..., description="Workspace ID")
    user_id: int = Field(..., description="User ID")
    channel_type: str = Field(..., description="Channel: web, slack, api")
    external_channel_id: Optional[str] = Field(None, description="External channel ID (e.g., Slack thread)")
    created_at: datetime = Field(..., description="Conversation start timestamp")
    updated_at: datetime = Field(..., description="Last message timestamp")
    message_count: Optional[int] = Field(None, description="Number of messages in conversation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "workspace_id": 1,
                "user_id": 5,
                "channel_type": "web",
                "external_channel_id": None,
                "created_at": "2024-01-15T10:25:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "message_count": 3,
            }
        }


class ConversationListResponse(BaseModel):
    """List of conversations."""
    
    conversations: List[Conversation] = Field(default_factory=list, description="List of conversations")
    total: int = Field(..., description="Total number of conversations")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Number of items per page")
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversations": [
                    {
                        "id": 1,
                        "workspace_id": 1,
                        "user_id": 5,
                        "channel_type": "web",
                        "external_channel_id": None,
                        "created_at": "2024-01-15T10:25:00Z",
                        "updated_at": "2024-01-15T10:30:00Z",
                        "message_count": 3,
                    }
                ],
                "total": 42,
                "page": 1,
                "page_size": 20,
            }
        }


class MessageListResponse(BaseModel):
    """List of messages in a conversation."""
    
    messages: List[Message] = Field(default_factory=list, description="List of messages")
    conversation_id: int = Field(..., description="Conversation ID")
    total: int = Field(..., description="Total number of messages")
    
    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {
                        "id": 1,
                        "conversation_id": 1,
                        "role": "user",
                        "content": "What is our OAuth 2.0 implementation?",
                        "citations": None,
                        "created_at": "2024-01-15T10:25:00Z",
                    },
                    {
                        "id": 2,
                        "conversation_id": 1,
                        "role": "assistant",
                        "content": "Our OAuth 2.0 implementation follows...",
                        "citations": [
                            {
                                "chunk_id": 123,
                                "document_id": 45,
                                "title": "API Authentication Guide",
                                "url": "https://confluence.example.com/pages/12345",
                                "score": 0.92,
                            }
                        ],
                        "created_at": "2024-01-15T10:25:30Z",
                    }
                ],
                "conversation_id": 1,
                "total": 2,
            }
        }
