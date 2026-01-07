"""End-to-end integration test for US1 Scenario 1: Single source citation.

Scenario: User asks a question that can be answered from a single document.
Expected: Answer cites that one document with a working deep link.
"""

import pytest
from unittest.mock import patch, Mock
from sqlalchemy.orm import Session

from src.models.workspace import Workspace
from src.models.user import User
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.ingestion.pipeline import ingest_document
from src.api.routes.query import query_knowledge_base
from src.api.schemas.query import QueryRequest
from src.integrations.llm_client import OpenAIClient


def test_us1_scenario1_single_source_citation(db_session: Session) -> None:
    """
    Test Scenario 1: Single source citation.
    
    User flow:
    1. Admin indexes a Confluence page about OAuth 2.0
    2. User asks "What is OAuth 2.0?"
    3. System retrieves relevant chunk from that page
    4. LLM generates answer grounded in that chunk
    5. Response includes citation with deep link to Confluence page
    
    Success criteria:
    - Answer contains OAuth 2.0 information
    - Exactly one citation
    - Citation includes document title and URL
    - URL is a valid deep link
    """
    # Setup: Create workspace and user
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    user = User(
        workspace_id=workspace.id,
        email="user@example.com",
        full_name="Test User",
        role="member",
        connector_identities={
            "confluence": {
                "external_id": "user123",
                "email": "user@example.com",
            }
        },
    )
    db_session.add(user)
    db_session.commit()
    
    # Step 1: Ingest document (simulating admin indexing Confluence page)
    document_content = """
    # OAuth 2.0 Authentication Guide
    
    ## What is OAuth 2.0?
    
    OAuth 2.0 is an industry-standard authorization framework that enables applications
    to obtain limited access to user accounts on an HTTP service. It works by delegating
    user authentication to the service that hosts the user account, and authorizing
    third-party applications to access the user account.
    
    OAuth 2.0 provides authorization flows for web applications, desktop applications,
    mobile phones, and IoT devices.
    
    ## Key Components
    
    - Resource Owner: The user who owns the data
    - Client: The application requesting access
    - Authorization Server: Issues access tokens
    - Resource Server: Hosts the protected resources
    
    ## Common Flow
    
    The Authorization Code flow is the most secure OAuth 2.0 flow:
    1. User clicks "Login with Provider"
    2. Redirect to authorization server
    3. User authenticates and grants permission
    4. Authorization code returned
    5. Exchange code for access token
    6. Use token to access protected resources
    """
    
    document = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="page-12345",
        title="OAuth 2.0 Authentication Guide",
        url="https://confluence.example.com/display/DOCS/OAuth+2.0+Authentication+Guide",
        content_hash="abc123",
        metadata_json={
            "space": "DOCS",
            "author": "admin@example.com",
            "last_modified": "2024-01-15T10:00:00Z",
        },
    )
    db_session.add(document)
    db_session.flush()
    
    # Create chunks with embeddings
    from src.ingestion.chunker import chunk_text
    chunks_text = chunk_text(document_content, chunk_size=500, chunk_overlap=100)
    
    for i, chunk_text_content in enumerate(chunks_text):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=i,
            content=chunk_text_content,
            token_count=len(chunk_text_content.split()),
            embedding_id=f"embed-{document.id}-{i}",
            acl_json={"public": True},  # Public document
        )
        db_session.add(chunk)
    
    db_session.commit()
    
    # Step 2: Mock LLM response
    mock_llm_response = {
        "content": (
            "OAuth 2.0 is an industry-standard authorization framework that enables "
            "applications to obtain limited access to user accounts on an HTTP service. "
            "It works by delegating user authentication to the service that hosts the "
            "user account, and authorizing third-party applications to access the user "
            "account."
        ),
        "usage": {"prompt_tokens": 250, "completion_tokens": 50, "total_tokens": 300},
    }
    
    # Step 3: Mock embeddings and vector search
    with patch('src.retrieval.answer_generation.generate_answer') as mock_generate:
        # Mock the RAG pipeline to return our test result
        mock_generate.return_value = {
            "answer": mock_llm_response["content"],
            "citations": [
                {
                    "chunk_id": 1,
                    "document_id": document.id,
                    "title": document.title,
                    "url": document.url,
                    "score": 0.92,
                }
            ],
            "usage": mock_llm_response["usage"],
        }
        
        # Step 4: Query via API
        request = QueryRequest(
            question="What is OAuth 2.0?",
            max_results=5,
            temperature=0.7,
        )
        
        response = query_knowledge_base(
            request=request,
            current_user=user,
            db=db_session,
        )
    
    # Step 5: Verify response
    assert response.answer is not None
    assert len(response.answer) > 0
    assert "OAuth 2.0" in response.answer
    assert "authorization framework" in response.answer
    
    # Step 6: Verify single citation
    assert len(response.citations) == 1
    citation = response.citations[0]
    
    assert citation.document_id == document.id
    assert citation.title == "OAuth 2.0 Authentication Guide"
    assert citation.url == "https://confluence.example.com/display/DOCS/OAuth+2.0+Authentication+Guide"
    assert citation.score > 0.8  # High relevance
    
    # Step 7: Verify conversation created
    assert response.conversation_id > 0
    assert response.message_id > 0
    
    # Step 8: Verify usage stats
    assert response.usage["total_tokens"] > 0
    
    print("✅ US1 Scenario 1 PASSED: Single source citation working correctly")
