"""Tests for Message model."""

import pytest
from sqlalchemy.orm import Session

from src.models.conversation import Conversation
from src.models.message import Message


def test_message_creation(db_session: Session) -> None:
    """Test creating a message."""
    # Create parent conversation first
    conversation = Conversation(
        workspace_id=1,
        user_id=1,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.commit()
    
    # Create user message
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content="What is our API authentication strategy?",
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)

    assert message.id is not None
    assert message.conversation_id == conversation.id
    assert message.role == "user"
    assert "authentication" in message.content
    assert message.citations_json == {}  # User messages don't have citations
    assert message.created_at is not None


def test_message_assistant_with_citations(db_session: Session) -> None:
    """Test creating an assistant message with citations."""
    conversation = Conversation(
        workspace_id=1,
        user_id=1,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.commit()
    
    # Assistant response with citations
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="We use OAuth 2.0 for API authentication. See the API docs for details.",
        citations_json={
            "citations": [
                {
                    "document_id": 123,
                    "chunk_id": 456,
                    "source_type": "confluence",
                    "title": "API Documentation",
                    "url": "https://company.atlassian.net/wiki/spaces/ENG/pages/123",
                    "snippet": "OAuth 2.0 is our standard...",
                }
            ]
        },
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    
    assert message.role == "assistant"
    assert "OAuth 2.0" in message.content
    assert len(message.citations_json["citations"]) == 1
    assert message.citations_json["citations"][0]["document_id"] == 123


def test_message_required_fields(db_session: Session) -> None:
    """Test that required fields are enforced."""
    message = Message(
        role="user",
        content="Question?",
    )
    db_session.add(message)
    
    with pytest.raises(Exception):  # Will raise IntegrityError (missing conversation_id)
        db_session.commit()


def test_message_ordering_in_conversation(db_session: Session) -> None:
    """Test that messages maintain chronological order."""
    conversation = Conversation(
        workspace_id=1,
        user_id=1,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.commit()
    
    # Create messages in sequence
    msg1 = Message(
        conversation_id=conversation.id,
        role="user",
        content="First question",
    )
    msg2 = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="First answer",
    )
    msg3 = Message(
        conversation_id=conversation.id,
        role="user",
        content="Follow-up question",
    )
    msg4 = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Follow-up answer",
    )
    db_session.add_all([msg1, msg2, msg3, msg4])
    db_session.commit()
    
    # Query messages in order
    messages = db_session.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.created_at).all()
    
    assert len(messages) == 4
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"
    assert messages[3].role == "assistant"


def test_message_system_role(db_session: Session) -> None:
    """Test system messages (e.g., context/instructions)."""
    conversation = Conversation(
        workspace_id=1,
        user_id=1,
        channel_type="slack",
        external_channel_id="C123",
    )
    db_session.add(conversation)
    db_session.commit()
    
    system_message = Message(
        conversation_id=conversation.id,
        role="system",
        content="You are a helpful assistant for answering questions about company documentation.",
    )
    db_session.add(system_message)
    db_session.commit()
    db_session.refresh(system_message)
    
    assert system_message.role == "system"
    assert "helpful assistant" in system_message.content


def test_message_citations_empty_by_default(db_session: Session) -> None:
    """Test that citations_json defaults to empty dict."""
    conversation = Conversation(
        workspace_id=1,
        user_id=1,
        channel_type="web",
    )
    db_session.add(conversation)
    db_session.commit()
    
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content="Question without citations",
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    
    assert message.citations_json == {}
