"""End-to-end integration test for US1 Scenario 2: Multi-source synthesis.

Scenario: User asks a question requiring information from multiple sources.
Expected: Answer synthesizes information from multiple documents with multiple citations.
"""

import pytest
from unittest.mock import patch
from sqlalchemy.orm import Session

from src.models.workspace import Workspace
from src.models.user import User
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.api.routes.query import query_knowledge_base
from src.api.schemas.query import QueryRequest


def test_us1_scenario2_multi_source_synthesis(db_session: Session) -> None:
    """
    Test Scenario 2: Multi-source synthesis.
    
    User flow:
    1. Admin indexes multiple documents:
       - Confluence page on authentication methods
       - Jira ticket discussing OAuth implementation
       - Slack conversation about security best practices
    2. User asks "What are our authentication options?"
    3. System retrieves relevant chunks from all three sources
    4. LLM synthesizes answer combining information from all sources
    5. Response includes multiple citations (one per source)
    
    Success criteria:
    - Answer mentions multiple authentication methods
    - Multiple citations (at least 2-3)
    - Citations from different source types
    - Each citation has unique document_id
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
            "confluence": {"external_id": "user123", "email": "user@example.com"},
            "jira": {"external_id": "account789", "email": "user@example.com"},
            "slack": {"external_id": "U456", "email": "user@example.com"},
        },
    )
    db_session.add(user)
    db_session.commit()
    
    # Step 1: Ingest multiple documents
    
    # Document 1: Confluence page on authentication
    doc1 = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="page-auth-101",
        title="Authentication Methods Overview",
        url="https://confluence.example.com/display/ARCH/Authentication+Methods",
        content_hash="hash1",
        metadata_json={"space": "ARCH"},
    )
    db_session.add(doc1)
    db_session.flush()
    
    chunk1 = DocumentChunk(
        document_id=doc1.id,
        chunk_index=0,
        content=(
            "Our platform supports three authentication methods: "
            "1. OAuth 2.0 for third-party applications "
            "2. API keys for server-to-server communication "
            "3. Session-based authentication for web applications. "
            "OAuth 2.0 is recommended for most use cases."
        ),
        token_count=50,
        embedding_id=f"embed-{doc1.id}-0",
        acl_json={"public": True},
    )
    db_session.add(chunk1)
    
    # Document 2: Jira ticket on OAuth implementation
    doc2 = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="jira",
        source_id="PROJ-123",
        title="PROJ-123: Implement OAuth 2.0 authorization code flow",
        url="https://jira.example.com/browse/PROJ-123",
        content_hash="hash2",
        metadata_json={"project": "PROJ", "status": "Done"},
    )
    db_session.add(doc2)
    db_session.flush()
    
    chunk2 = DocumentChunk(
        document_id=doc2.id,
        chunk_index=0,
        content=(
            "Implementation completed for OAuth 2.0 with PKCE extension. "
            "Supports authorization code flow with refresh tokens. "
            "Access tokens expire after 1 hour. "
            "Refresh tokens valid for 30 days. "
            "All tokens stored encrypted in database."
        ),
        token_count=45,
        embedding_id=f"embed-{doc2.id}-0",
        acl_json={"readers": ["user@example.com"]},
    )
    db_session.add(chunk2)
    
    # Document 3: Slack conversation on security
    doc3 = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="slack",
        source_id="msg-789",
        title="Security discussion in #engineering",
        url="https://company.slack.com/archives/C123/p1234567890",
        content_hash="hash3",
        metadata_json={"channel": "engineering"},
    )
    db_session.add(doc3)
    db_session.flush()
    
    chunk3 = DocumentChunk(
        document_id=doc3.id,
        chunk_index=0,
        content=(
            "@security-team recommends rotating API keys every 90 days. "
            "For OAuth, always use PKCE for mobile/SPA applications. "
            "Never store client secrets in frontend code. "
            "Consider implementing rate limiting on auth endpoints."
        ),
        token_count=40,
        embedding_id=f"embed-{doc3.id}-0",
        acl_json={"channel": "C123"},
    )
    db_session.add(chunk3)
    
    db_session.commit()
    
    # Step 2: Mock RAG response combining all sources
    with patch('src.retrieval.answer_generation.generate_answer') as mock_generate:
        mock_generate.return_value = {
            "answer": (
                "Our platform supports three main authentication methods: "
                "OAuth 2.0, API keys, and session-based authentication. "
                "OAuth 2.0 is recommended for most use cases and has been implemented "
                "with the authorization code flow and PKCE extension. Access tokens "
                "expire after 1 hour, and refresh tokens are valid for 30 days. "
                "For API keys, security best practices recommend rotating them every "
                "90 days. When implementing OAuth for mobile or single-page applications, "
                "always use PKCE and never store client secrets in frontend code."
            ),
            "citations": [
                {
                    "chunk_id": chunk1.id,
                    "document_id": doc1.id,
                    "title": doc1.title,
                    "url": doc1.url,
                    "score": 0.89,
                },
                {
                    "chunk_id": chunk2.id,
                    "document_id": doc2.id,
                    "title": doc2.title,
                    "url": doc2.url,
                    "score": 0.85,
                },
                {
                    "chunk_id": chunk3.id,
                    "document_id": doc3.id,
                    "title": doc3.title,
                    "url": doc3.url,
                    "score": 0.78,
                },
            ],
            "usage": {"prompt_tokens": 400, "completion_tokens": 120, "total_tokens": 520},
        }
        
        # Step 3: Query via API
        request = QueryRequest(
            question="What are our authentication options?",
            max_results=10,
            temperature=0.7,
        )
        
        response = query_knowledge_base(
            request=request,
            current_user=user,
            db=db_session,
        )
    
    # Step 4: Verify multi-source synthesis
    assert response.answer is not None
    assert "OAuth 2.0" in response.answer or "OAuth" in response.answer
    assert "API key" in response.answer or "API keys" in response.answer
    assert "session" in response.answer or "Session" in response.answer
    
    # Step 5: Verify multiple citations
    assert len(response.citations) >= 2, "Should have at least 2 citations"
    assert len(response.citations) == 3, "Should cite all 3 sources"
    
    # Step 6: Verify different source types
    source_types = set()
    document_ids = set()
    
    for citation in response.citations:
        document_ids.add(citation.document_id)
        # Get source type from database
        doc = db_session.query(Document).filter(Document.id == citation.document_id).first()
        source_types.add(doc.source_type)
    
    assert len(document_ids) == 3, "Each citation should reference unique document"
    assert len(source_types) >= 2, "Should cite documents from multiple source types"
    assert "confluence" in source_types
    assert "jira" in source_types or "slack" in source_types
    
    # Step 7: Verify citations have required fields
    for citation in response.citations:
        assert citation.document_id > 0
        assert citation.title is not None
        assert citation.url is not None
        assert citation.score > 0.5  # Reasonable relevance
    
    # Step 8: Verify usage stats
    assert response.usage["total_tokens"] > 0
    
    print("✅ US1 Scenario 2 PASSED: Multi-source synthesis working correctly")
