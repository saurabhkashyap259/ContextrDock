"""Vector similarity search using Qdrant."""

from typing import Any

from sqlalchemy.orm import Session

from src.ingestion.embeddings import EmbeddingService
from src.integrations.vector_db import QdrantClient
from src.models.document import Document
from src.models.document_chunk import DocumentChunk


def search_by_vector(
    db_session: Session,
    query: str,
    workspace_id: int,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Search document chunks using vector similarity.

    Process:
    1. Generate embedding for query
    2. Search Qdrant for similar vectors
    3. Enrich results with chunk data from PostgreSQL

    Args:
        db_session: Database session
        query: Search query string
        workspace_id: Workspace ID for filtering
        top_k: Maximum number of results to return

    Returns:
        List of search results with metadata and scores

    Example:
        >>> results = search_by_vector(
        ...     db_session=session,
        ...     query="How do I authenticate to the API?",
        ...     workspace_id=1,
        ...     top_k=5,
        ... )
        >>> results[0]["score"]
        0.92
    """
    if not query or not query.strip():
        return []

    # Step 1: Generate embedding for query
    embedding_service = EmbeddingService()
    query_embedding = embedding_service.embed_text(query)

    # Step 2: Search Qdrant for similar vectors
    qdrant_client = QdrantClient()
    vector_results = qdrant_client.search_vectors(
        query_embedding=query_embedding,
        top_k=top_k,
        filters={"workspace_id": workspace_id},
    )

    if not vector_results:
        return []

    # Step 3: Enrich with chunk data from PostgreSQL
    chunk_ids = [result["metadata"].get("chunk_id") for result in vector_results]
    chunk_ids = [cid for cid in chunk_ids if cid is not None]

    if not chunk_ids:
        return []

    # Query database for chunk details
    chunks_query = db_session.query(
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
    ).join(
        Document, DocumentChunk.document_id == Document.id
    ).filter(
        DocumentChunk.id.in_(chunk_ids)
    )

    # Create lookup dict
    chunks_dict = {row.chunk_id: row for row in chunks_query.all()}

    # Merge Qdrant results with database data
    results = []
    for vector_result in vector_results:
        chunk_id = vector_result["metadata"].get("chunk_id")
        if chunk_id not in chunks_dict:
            continue

        chunk_data = chunks_dict[chunk_id]
        results.append({
            "chunk_id": chunk_data.chunk_id,
            "document_id": chunk_data.document_id,
            "content": chunk_data.content,
            "chunk_index": chunk_data.chunk_index,
            "acl": chunk_data.acl,
            "title": chunk_data.title,
            "url": chunk_data.url,
            "source_type": chunk_data.source_type,
            "source_id": chunk_data.source_id,
            "workspace_id": chunk_data.workspace_id,
            "score": vector_result["score"],
        })

    return results
