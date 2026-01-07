"""Conversation API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.schemas.query import (
    Conversation as ConversationSchema,
    ConversationListResponse,
    Message as MessageSchema,
    MessageListResponse,
    Citation,
)
from src.api.middleware.auth import get_current_user
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.database import get_db


router = APIRouter(prefix="/v1", tags=["conversations"])


@router.get("/conversations", response_model=ConversationListResponse, status_code=status.HTTP_200_OK)
def list_conversations(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    """
    List user's conversations with pagination.
    
    Returns conversations ordered by most recent activity first.
    Includes message count for each conversation.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page (1-100)
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Paginated list of conversations
    """
    # Count total conversations
    total = db.query(func.count(Conversation.id)).filter(
        Conversation.workspace_id == current_user.workspace_id,
        Conversation.user_id == current_user.id,
    ).scalar()
    
    # Get paginated conversations
    offset = (page - 1) * page_size
    conversations = (
        db.query(
            Conversation,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.workspace_id == current_user.workspace_id,
            Conversation.user_id == current_user.id,
        )
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    
    # Build response
    conversation_list = [
        ConversationSchema(
            id=conv.id,
            workspace_id=conv.workspace_id,
            user_id=conv.user_id,
            channel_type=conv.channel_type,
            external_channel_id=conv.external_channel_id,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=message_count,
        )
        for conv, message_count in conversations
    ]
    
    return ConversationListResponse(
        conversations=conversation_list,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse, status_code=status.HTTP_200_OK)
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageListResponse:
    """
    Get all messages in a conversation.
    
    Returns messages ordered chronologically (oldest first).
    Only accessible to the conversation owner.
    
    Args:
        conversation_id: Conversation ID
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of messages with citations
        
    Raises:
        404: Conversation not found or access denied
    """
    # Verify conversation exists and belongs to user
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.workspace_id == current_user.workspace_id,
        Conversation.user_id == current_user.id,
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied"
        )
    
    # Get messages
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    
    # Build response
    message_list = []
    for msg in messages:
        citations = None
        if msg.citations_json:
            citations = [
                Citation(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    title=c.get("title"),
                    url=c.get("url"),
                    score=c["score"],
                )
                for c in msg.citations_json
            ]
        
        message_list.append(
            MessageSchema(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                citations=citations,
                created_at=msg.created_at,
            )
        )
    
    return MessageListResponse(
        messages=message_list,
        conversation_id=conversation_id,
        total=len(message_list),
    )
