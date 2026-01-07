"""Integration tests for POST /v1/query endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.main import app
from src.models.workspace import Workspace
from src.models.user import User
from src.models.document import Document
from src.models.document_chunk import DocumentChunk


client = TestClient(app)


def test_query_endpoint_returns_answer_with_citations(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that query endpoint returns answer with citations."""
    # Create test document and chunk
    document = Document(
        workspace_id=test_user.workspace_id,
        connector_id=None,
        source_type="confluence",
        source_id="12345",
        title="OAuth Guide",
        url="https://confluence.example.com/pages/12345",
        content_hash="abc123",
        metadata_json={},
    )
    db_session.add(document)
    db_session.flush()
    
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="OAuth 2.0 is an authorization framework for secure API access.",
        token_count=15,
        embedding_id="embed-123",
        acl_json={"public": True},
    )
    db_session.add(chunk)
    db_session.commit()
    
    # Mock LLM and vector DB (these would be mocked in actual tests)
    # For integration test, we'll skip this and test with real services
    
    request_data = {
        "question": "What is OAuth 2.0?",
        "max_results": 5,
        "temperature": 0.7,
    }
    
    response = client.post("/v1/query", json=request_data, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert "citations" in data
    assert "conversation_id" in data
    assert "message_id" in data
    assert "usage" in data
    
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert isinstance(data["citations"], list)


def test_query_endpoint_creates_conversation(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that query creates a new conversation."""
    request_data = {
        "question": "Test question",
        "max_results": 5,
    }
    
    response = client.post("/v1/query", json=request_data, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    conversation_id = data["conversation_id"]
    assert conversation_id > 0
    
    # Verify conversation exists in database
    from src.models.conversation import Conversation
    conversation = db_session.query(Conversation).filter(Conversation.id == conversation_id).first()
    assert conversation is not None
    assert conversation.workspace_id == test_user.workspace_id
    assert conversation.user_id == test_user.id


def test_query_endpoint_continues_conversation(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that query can continue existing conversation."""
    from src.models.conversation import Conversation
    from src.models.message import Message
    
    # Create existing conversation
    conversation = Conversation(
        workspace_id=test_user.workspace_id,
        user_id=test_user.id,
        channel_type="web",
        external_channel_id=None,
    )
    db_session.add(conversation)
    db_session.flush()
    
    # Add previous message
    message = Message(
        conversation_id=conversation.id,
        role="user",
        content="Previous question",
        citations_json=None,
    )
    db_session.add(message)
    db_session.commit()
    
    request_data = {
        "question": "Follow-up question",
        "conversation_id": conversation.id,
        "max_results": 5,
    }
    
    response = client.post("/v1/query", json=request_data, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should use same conversation
    assert data["conversation_id"] == conversation.id


def test_query_endpoint_requires_authentication(db_session: Session) -> None:
    """Test that query endpoint requires authentication."""
    request_data = {
        "question": "Test question",
    }
    
    response = client.post("/v1/query", json=request_data)
    
    assert response.status_code == 401


def test_query_endpoint_validates_input(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that query endpoint validates input."""
    # Empty question
    response = client.post("/v1/query", json={"question": ""}, headers=auth_headers)
    assert response.status_code == 422
    
    # Missing question
    response = client.post("/v1/query", json={}, headers=auth_headers)
    assert response.status_code == 422
    
    # Invalid max_results
    response = client.post("/v1/query", json={"question": "Test", "max_results": -1}, headers=auth_headers)
    assert response.status_code == 422
    
    # Invalid temperature
    response = client.post("/v1/query", json={"question": "Test", "temperature": 3.0}, headers=auth_headers)
    assert response.status_code == 422


def test_query_endpoint_handles_no_results(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test query endpoint when no relevant documents found."""
    request_data = {
        "question": "Very specific question with no matches",
        "max_results": 5,
    }
    
    response = client.post("/v1/query", json=request_data, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should still return an answer (explaining no results)
    assert "answer" in data
    assert "citations" in data
    assert len(data["citations"]) == 0


def test_query_endpoint_respects_workspace_isolation(db_session: Session, test_user: User, auth_headers: dict) -> None:
    """Test that query only accesses documents in user's workspace."""
    # Create document in different workspace
    other_workspace = Workspace(name="Other Workspace")
    db_session.add(other_workspace)
    db_session.flush()
    
    document = Document(
        workspace_id=other_workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="99999",
        title="Private Doc",
        url="https://example.com",
        content_hash="xyz789",
        metadata_json={},
    )
    db_session.add(document)
    db_session.commit()
    
    request_data = {
        "question": "Private Doc",
        "max_results": 5,
    }
    
    response = client.post("/v1/query", json=request_data, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should not find document from other workspace
    for citation in data["citations"]:
        assert citation["document_id"] != document.id
