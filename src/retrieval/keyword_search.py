"""BM25 keyword search using PostgreSQL full-text search."""

from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.models.document import Document
from src.models.document_chunk import DocumentChunk


def search_by_keywords(
    db_session: Session,
    query: str,
    workspace_id: int,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Search document chunks using BM25-style keyword matching.

    Uses PostgreSQL's built-in full-text search with ts_rank for relevance scoring.

    Args:
        db_session: Database session
        query: Search query string
        workspace_id: Workspace ID for filtering
        top_k: Maximum number of results to return

    Returns:
        List of search results with metadata and scores

    Example:
        >>> results = search_by_keywords(
        ...     db_session=session,
        ...     query="API authentication OAuth",
        ...     workspace_id=1,
        ...     top_k=5,
        ... )
        >>> len(results)
        5
        >>> results[0]["score"]
        0.8
    """
    if not query or not query.strip():
        return []

    # PostgreSQL full-text search query
    # ts_rank provides BM25-like relevance scoring
    search_query = db_session.query(
        DocumentChunk.id.label("chunk_id"),
        DocumentChunk.document_id,
        DocumentChunk.content,
        DocumentChunk.chunk_index,
        DocumentChunk.acl_json.label("acl"),
        Document.title,
        Document.url,
        Document.source_type,
        Document.source_id,
        Document.workspace_id,
        func.ts_rank(
            func.to_tsvector('english', DocumentChunk.content),
            func.plainto_tsquery('english', query)
        ).label("score")
    ).join(
        Document, DocumentChunk.document_id == Document.id
    ).filter(
        Document.workspace_id == workspace_id,
        func.to_tsvector('english', DocumentChunk.content).op('@@')(
            func.plainto_tsquery('english', query)
        )
    ).order_by(
        text("score DESC")
    ).limit(top_k)

    results = []
    for row in search_query.all():
        results.append({
            "chunk_id": row.chunk_id,
            "document_id": row.document_id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "acl": row.acl,
            "title": row.title,
            "url": row.url,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "workspace_id": row.workspace_id,
            "score": float(row.score) if row.score else 0.0,
        })

    return results
