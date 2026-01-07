"""RAG-based answer generation with grounded citations."""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.integrations.llm_client import LLMClient
from src.retrieval.hybrid_search import hybrid_search
from src.retrieval.acl_filter import filter_by_permissions
from src.services.identity_resolution import resolve_user_identities


def generate_answer(
    db_session: Session,
    query: str,
    user_id: int,
    workspace_id: int,
    llm_client: LLMClient,
    max_context_chunks: int = 10,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """
    Generate an answer using RAG (Retrieval-Augmented Generation).
    
    Process:
    1. Resolve user's connector identities
    2. Retrieve relevant chunks using hybrid search
    3. Filter by ACL permissions
    4. Build prompt with context
    5. Generate answer using LLM
    6. Return answer with grounded citations
    
    Args:
        db_session: Database session
        query: User's question
        user_id: User ID for ACL filtering
        workspace_id: Workspace ID
        llm_client: LLM client instance
        max_context_chunks: Maximum chunks to include in prompt
        temperature: LLM sampling temperature
        
    Returns:
        Dict with 'answer', 'citations', and 'usage' keys
        
    Example:
        >>> llm = OpenAIClient(api_key="...", model="gpt-4")
        >>> result = generate_answer(
        ...     db_session=session,
        ...     query="What is OAuth 2.0?",
        ...     user_id=1,
        ...     workspace_id=1,
        ...     llm_client=llm,
        ... )
        >>> result["answer"]
        'OAuth 2.0 is an authorization framework...'
        >>> result["citations"]
        [{"document_id": 100, "title": "OAuth Guide", ...}]
    """
    # Step 1: Resolve user identities for ACL checking
    user_identities = resolve_user_identities(db_session, user_id=user_id)
    
    if not user_identities:
        user_identities = []
    
    # Step 2: Retrieve relevant chunks
    search_results = hybrid_search(
        db_session=db_session,
        query=query,
        workspace_id=workspace_id,
        top_k=max_context_chunks * 2,  # Retrieve more for better filtering
    )
    
    # Step 3: Filter by permissions
    permitted_results = filter_by_permissions(search_results, user_identities)
    
    # Limit to max_context_chunks
    permitted_results = permitted_results[:max_context_chunks]
    
    # Step 4: Handle no results case
    if not permitted_results:
        return {
            "answer": "I couldn't find any relevant information to answer your question. This could be because:\n"
                     "- No documents match your query\n"
                     "- You don't have permission to access relevant documents\n"
                     "- The information hasn't been indexed yet",
            "citations": [],
            "usage": {"total_tokens": 0},
        }
    
    # Step 5: Build prompt with context
    context_text = _build_context_from_chunks(permitted_results)
    
    system_message = f"""You are a helpful assistant that answers questions based on the provided context.

IMPORTANT INSTRUCTIONS:
1. Base your answer ONLY on the provided context
2. If the context doesn't contain the answer, say so clearly
3. Be concise and accurate
4. Cite specific sources when making claims
5. Do not make up information or use external knowledge

CONTEXT:
{context_text}

Remember: Only use information from the context above."""
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": query},
    ]
    
    # Step 6: Generate answer
    response = llm_client.generate(messages, temperature=temperature)
    
    # Step 7: Build citations
    citations = [
        {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "title": chunk.get("title"),
            "url": chunk.get("url"),
            "score": chunk["score"],
        }
        for chunk in permitted_results
    ]
    
    return {
        "answer": response["content"],
        "citations": citations,
        "usage": response["usage"],
    }


def _build_context_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    """
    Build formatted context text from search results.
    
    Args:
        chunks: List of permitted search results
        
    Returns:
        Formatted context string for LLM prompt
    """
    context_parts = []
    
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.get("title", "Untitled")
        url = chunk.get("url", "No URL")
        content = chunk["content"]
        
        context_parts.append(
            f"[Source {i}] {title}\n"
            f"URL: {url}\n"
            f"Content: {content}\n"
        )
    
    return "\n---\n\n".join(context_parts)


def stream_answer(
    db_session: Session,
    query: str,
    user_id: int,
    workspace_id: int,
    llm_client: LLMClient,
    max_context_chunks: int = 10,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """
    Stream answer generation (for real-time UX).
    
    Same as generate_answer but returns an iterator for streaming.
    
    Args:
        db_session: Database session
        query: User's question
        user_id: User ID
        workspace_id: Workspace ID
        llm_client: LLM client instance
        max_context_chunks: Maximum chunks in context
        temperature: LLM temperature
        
    Returns:
        Dict with 'stream' (iterator) and 'citations' keys
    """
    # Retrieve and filter (same as generate_answer)
    user_identities = resolve_user_identities(db_session, user_id=user_id)
    if not user_identities:
        user_identities = []
    
    search_results = hybrid_search(
        db_session=db_session,
        query=query,
        workspace_id=workspace_id,
        top_k=max_context_chunks * 2,
    )
    
    permitted_results = filter_by_permissions(search_results, user_identities)
    permitted_results = permitted_results[:max_context_chunks]
    
    if not permitted_results:
        def empty_stream():
            yield "I couldn't find any relevant information to answer your question."
        
        return {
            "stream": empty_stream(),
            "citations": [],
        }
    
    # Build prompt
    context_text = _build_context_from_chunks(permitted_results)
    
    system_message = f"""You are a helpful assistant that answers questions based on the provided context.

Base your answer ONLY on the provided context. Be concise and accurate.

CONTEXT:
{context_text}"""
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": query},
    ]
    
    # Stream response
    stream = llm_client.stream(messages, temperature=temperature)
    
    # Build citations
    citations = [
        {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "title": chunk.get("title"),
            "url": chunk.get("url"),
            "score": chunk["score"],
        }
        for chunk in permitted_results
    ]
    
    return {
        "stream": stream,
        "citations": citations,
    }
