"""Integration tests for conversation endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.main import app
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message


client = TestClient(app)


def test_get_conversations_returns_list(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test GET /v1/conversations returns list of conversations."""
    # Create test conversations
    for i in range(3):
        conversation = Conversation(
            workspace_id=test_user.workspace_id,
            user_id=test_user.id,
            channel_type="web",
            external_channel_id=None,
        )
        db_session.add(conversation)
    db_session.commit()
    
    response = client.get("/v1/conversations", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "conversations" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    
    assert len(data["conversations"]) == 3
    assert data["total"] == 3


def test_get_conversations_only_returns_user_conversations(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that conversations are filtered by user."""
    # Create conversation for current user
    own_conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=test_user.id,
        channel_type="web",
    )
    db_session.add(own_conversation)
    
    # Create another user and their conversation
    other_user = User(
        workspace_id=test_user.workspace_id,
        email="other@example.com",
        full_name="Other User",
        role="member",
    )
    db_session.add(other_user)
    db_session.flush()
    
    other_conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=other_user.id,
        channel_type="web",
    )
    db_session.add(other_conversation)
    db_session.commit()
    
    response = client.get("/v1/conversations", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should only see own conversation
    assert data["total"] == 1
    assert data["conversations"][0]["user_id"] == test_user.id


def test_get_conversations_supports_pagination(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test pagination parameters for conversations list."""
    # Create 25 conversations
    for i in range(25):
        conversation = Conversation(
            workspace_id=test_user.workspace_id,
            user_id=test_user.id,
            channel_type="web",
        )
        db_session.add(conversation)
    db_session.commit()
    
    # Get first page
    response = client.get("/v1/conversations?page=1&page_size=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["conversations"]) == 10
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 10
    
    # Get second page
    response = client.get("/v1/conversations?page=2&page_size=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["conversations"]) == 10
    assert data["page"] == 2


def test_get_conversations_includes_message_count(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that conversations include message count."""
    conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=test_user.id,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.flush()
    
    # Add messages
    for i in range(5):
        message = Message(
            conversation_id=conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
        )
        db_session.add(message)
    db_session.commit()
    
    response = client.get("/v1/conversations", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["conversations"][0]["message_count"] == 5


def test_get_conversations_requires_authentication(db_session: Session) -> None:
    """Test that conversations endpoint requires authentication."""
    response = client.get("/v1/conversations")
    
    assert response.status_code == 401


def test_get_conversation_messages_returns_list(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test GET /v1/conversations/{id}/messages returns messages."""
    conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=test_user.id,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.flush()
    
    # Add messages
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content="Question",
    )
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Answer",
        citations_json=[{"document_id": 1, "chunk_id": 1, "title": "Doc", "url": None, "score": 0.9}],
    )
    db_session.add_all([user_msg, assistant_msg])
    db_session.commit()
    
    response = client.get(f"/v1/conversations/{conversation.id}/messages", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "messages" in data
    assert "conversation_id" in data
    assert "total" in data
    
    assert len(data["messages"]) == 2
    assert data["total"] == 2
    assert data["conversation_id"] == conversation.id
    
    # Check message structure
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["citations"] is not None


def test_get_conversation_messages_denies_other_user_access(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that users can't access other users' conversations."""
    # Create another user's conversation
    other_user = User(
        workspace_id=test_user.workspace_id,
        email="other@example.com",
        full_name="Other User",
        role="member",
    )
    db_session.add(other_user)
    db_session.flush()
    
    conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=other_user.id,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.commit()
    
    response = client.get(f"/v1/conversations/{conversation.id}/messages", headers=auth_headers)
    
    assert response.status_code == 404


def test_get_conversation_messages_not_found(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test 404 for non-existent conversation."""
    response = client.get("/v1/conversations/99999/messages", headers=auth_headers)
    
    assert response.status_code == 404


def test_get_conversation_messages_requires_authentication(db_session: Session) -> None:
    """Test that messages endpoint requires authentication."""
    response = client.get("/v1/conversations/1/messages")
    
    assert response.status_code == 401
