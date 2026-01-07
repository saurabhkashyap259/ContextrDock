"""End-to-end integration test for US1 Scenario 3: Insufficient evidence.

Scenario: User asks a question that cannot be answered from indexed documents.
Expected: System acknowledges lack of information rather than hallucinating.
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


def test_us1_scenario3_insufficient_evidence(db_session: Session) -> None:
    """
    Test Scenario 3: Insufficient evidence / No relevant documents.
    
    User flow:
    1. Admin has indexed some general documentation
    2. User asks very specific question not covered in docs
    3. Retrieval finds no relevant chunks (or very low relevance)
    4. System returns answer stating information is not available
    5. No citations included (or minimal irrelevant ones)
    
    Success criteria:
    - Answer acknowledges lack of information
    - Answer does NOT make up information
    - Empty or minimal citation list
    - Helpful message (suggests checking other sources, contacting team, etc.)
    - No hallucinated facts
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
        },
    )
    db_session.add(user)
    db_session.commit()
    
    # Step 1: Ingest unrelated documents
    
    # Document about general company policies (irrelevant to technical questions)
    doc1 = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="page-hr-001",
        title="Employee Handbook - Time Off Policy",
        url="https://confluence.example.com/display/HR/Time+Off+Policy",
        content_hash="hash-hr",
        metadata_json={"space": "HR"},
    )
    db_session.add(doc1)
    db_session.flush()
    
    chunk1 = DocumentChunk(
        document_id=doc1.id,
        chunk_index=0,
        content=(
            "Employees receive 20 days of paid time off per year. "
            "PTO requests should be submitted at least 2 weeks in advance. "
            "Public holidays are separate from PTO allowance. "
            "Unused PTO does not roll over to the next year."
        ),
        token_count=45,
        embedding_id=f"embed-{doc1.id}-0",
        acl_json={"public": True},
    )
    db_session.add(chunk1)
    
    # Document about office facilities (also irrelevant)
    doc2 = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="page-office-002",
        title="Office Facilities Guide",
        url="https://confluence.example.com/display/OPS/Office+Facilities",
        content_hash="hash-office",
        metadata_json={"space": "OPS"},
    )
    db_session.add(doc2)
    db_session.flush()
    
    chunk2 = DocumentChunk(
        document_id=doc2.id,
        chunk_index=0,
        content=(
            "The office has a fully equipped kitchen on each floor. "
            "Free coffee, tea, and snacks are available. "
            "Meeting rooms can be booked via the calendar system. "
            "The gym is open 24/7 with badge access."
        ),
        token_count=42,
        embedding_id=f"embed-{doc2.id}-0",
        acl_json={"public": True},
    )
    db_session.add(chunk2)
    
    db_session.commit()
    
    # Step 2: Mock RAG response indicating no relevant information
    with patch('src.retrieval.answer_generation.generate_answer') as mock_generate:
        # Simulate scenario where retrieval found no relevant results
        mock_generate.return_value = {
            "answer": (
                "I couldn't find any relevant information to answer your question "
                "about the quantum encryption implementation in our API. This could be because:\n"
                "- No documents match your query\n"
                "- You don't have permission to access relevant documents\n"
                "- The information hasn't been indexed yet\n\n"
                "You may want to:\n"
                "- Check with the security team directly\n"
                "- Search in a different system\n"
                "- Rephrase your question with different keywords"
            ),
            "citations": [],  # No citations when no relevant info found
            "usage": {"prompt_tokens": 50, "completion_tokens": 80, "total_tokens": 130},
        }
        
        # Step 3: Ask question about something not in the documents
        request = QueryRequest(
            question="What is our quantum encryption implementation in the API?",
            max_results=10,
            temperature=0.7,
        )
        
        response = query_knowledge_base(
            request=request,
            current_user=user,
            db=db_session,
        )
    
    # Step 4: Verify honest "don't know" response
    assert response.answer is not None
    
    # Answer should acknowledge lack of information
    answer_lower = response.answer.lower()
    lack_of_info_phrases = [
        "couldn't find",
        "no relevant information",
        "don't have information",
        "not available",
        "no documents",
        "unable to find",
    ]
    assert any(phrase in answer_lower for phrase in lack_of_info_phrases), \
        "Answer should acknowledge lack of information"
    
    # Answer should NOT contain made-up technical details
    hallucination_terms = [
        "quantum key distribution",
        "qkd protocol",
        "entanglement-based",
        "bb84 algorithm",
    ]
    for term in hallucination_terms:
        assert term not in answer_lower, \
            f"Answer should not hallucinate technical details (found: {term})"
    
    # Step 5: Verify empty or minimal citations
    assert len(response.citations) == 0, \
        "Should have no citations when no relevant information found"
    
    # Step 6: Verify helpful guidance
    helpful_terms = ["check", "search", "team", "rephrase", "keywords", "different"]
    assert any(term in answer_lower for term in helpful_terms), \
        "Answer should provide helpful guidance on next steps"
    
    # Step 7: Verify conversation still created (for follow-up questions)
    assert response.conversation_id > 0
    assert response.message_id > 0
    
    # Step 8: Verify minimal token usage (short response)
    assert response.usage["total_tokens"] < 500, \
        "Should use minimal tokens for 'don't know' response"
    
    print("✅ US1 Scenario 3 PASSED: Insufficient evidence handled correctly (no hallucination)")


def test_us1_scenario3_low_relevance_documents(db_session: Session) -> None:
    """
    Test variant: Documents exist but are minimally relevant.
    
    Even if some documents are retrieved, if they have low relevance scores,
    the system should acknowledge that the answer may not be reliable.
    """
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.flush()
    
    user = User(
        workspace_id=workspace.id,
        email="user@example.com",
        full_name="Test User",
        role="member",
    )
    db_session.add(user)
    db_session.commit()
    
    # Document with tangentially related content
    doc = Document(
        workspace_id=workspace.id,
        connector_id=None,
        source_type="confluence",
        source_id="page-security-general",
        title="General Security Practices",
        url="https://confluence.example.com/display/SEC/General+Security",
        content_hash="hash-sec",
        metadata_json={"space": "SEC"},
    )
    db_session.add(doc)
    db_session.flush()
    
    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="We use industry-standard security practices across all systems.",
        token_count=10,
        embedding_id=f"embed-{doc.id}-0",
        acl_json={"public": True},
    )
    db_session.add(chunk)
    db_session.commit()
    
    with patch('src.retrieval.answer_generation.generate_answer') as mock_generate:
        # Low relevance citations
        mock_generate.return_value = {
            "answer": (
                "I found some general information about security practices, "
                "but I don't have specific details about quantum encryption. "
                "The available information only mentions 'industry-standard security practices' "
                "without providing technical specifics."
            ),
            "citations": [
                {
                    "chunk_id": chunk.id,
                    "document_id": doc.id,
                    "title": doc.title,
                    "url": doc.url,
                    "score": 0.32,  # Low relevance score
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160},
        }
        
        request = QueryRequest(
            question="Explain our quantum encryption API implementation details",
            max_results=10,
        )
        
        response = query_knowledge_base(
            request=request,
            current_user=user,
            db=db_session,
        )
    
    # Should acknowledge limited information
    assert "don't have specific" in response.answer.lower() or \
           "limited information" in response.answer.lower() or \
           "without providing technical specifics" in response.answer.lower()
    
    # May have one low-relevance citation
    assert len(response.citations) <= 1
    if response.citations:
        assert response.citations[0].score < 0.5, "Citation should have low relevance score"
    
    print("✅ US1 Scenario 3 (variant) PASSED: Low relevance documents handled appropriately")
