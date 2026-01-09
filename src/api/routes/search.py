"""API routes for semantic search."""

import logging
import time
from typing import List, Optional

import openai
from fastapi import APIRouter, Depends, HTTPException, status
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.api.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchResultMetadata,
    SearchStatsResponse,
)
from src.config.settings import Settings
from src.database import get_db
from src.models.document import Document
from src.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter(prefix="/v1/search", tags=["search"])

# Initialize clients
openai_client = openai.OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

COLLECTION_NAME = "contextdock"
EMBEDDING_MODEL = "text-embedding-3-small"


def get_workspace_id() -> int:
    """Get workspace ID from auth context.

    TODO: Replace with actual auth/workspace resolution
    For now, returns hardcoded workspace ID for development.
    """
    return 1


def generate_query_embedding(query: str) -> List[float]:
    """
    Generate embedding for search query using OpenAI.

    Args:
        query: Search query text

    Returns:
        Embedding vector (1536 dimensions)

    Raises:
        HTTPException: If embedding generation fails
    """
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=query,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate query embedding",
        )


@router.post("", response_model=SearchResponse, status_code=status.HTTP_200_OK)
async def search_documents(
    request: SearchRequest,
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """
    Perform semantic search across indexed documents.

    This endpoint uses OpenAI embeddings and Qdrant vector database to perform
    semantic search over all indexed documents (Slack messages, Confluence pages, etc.).

    Args:
        request: Search request with query and filters
        workspace_id: Current workspace ID from auth context
        db: Database session

    Returns:
        SearchResponse with ranked results

    Example:
        ```json
        {
            "query": "user engagement strategies",
            "limit": 10,
            "offset": 0,
            "channel_id": "CGREG0X9A",
            "min_score": 0.3
        }
        ```
    """
    start_time = time.time()

    # Generate query embedding
    logger.info(f"Searching for: '{request.query}' (workspace_id={workspace_id})")
    query_embedding = generate_query_embedding(request.query)

    # Build Qdrant filter
    filter_conditions = []

    # Always filter by workspace
    filter_conditions.append(
        FieldCondition(
            key="workspace_id",
            match=MatchValue(value=workspace_id),
        )
    )

    # Optional source type filter
    if request.source_type:
        filter_conditions.append(
            FieldCondition(
                key="source_type",
                match=MatchValue(value=request.source_type),
            )
        )

    # Optional channel filter (for Slack)
    if request.channel_id:
        filter_conditions.append(
            FieldCondition(
                key="channel_id",
                match=MatchValue(value=request.channel_id),
            )
        )

    query_filter = Filter(must=filter_conditions) if filter_conditions else None

    # Perform vector search
    try:
        search_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=request.limit + request.offset,  # Fetch more for offset
            with_payload=True,
        )
    except Exception as e:
        logger.error(f"Qdrant search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vector search failed",
        )

    # Apply offset and min_score filter
    filtered_results = [
        r for r in search_results[request.offset:]
        if r.score >= request.min_score
    ][:request.limit]

    # Build response results
    results = []
    for result in filtered_results:
        payload = result.payload

        # Build metadata
        metadata = SearchResultMetadata(
            source_type=payload.get("source_type", "unknown"),
            source_id=payload.get("source_id", ""),
            channel_id=payload.get("channel_id"),
            channel_name=payload.get("channel_name"),
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            message_ts=payload.get("message_ts"),
        )

        # Build result
        search_result = SearchResult(
            id=payload.get("document_id", 0),
            title=payload.get("title", "")[:200],  # Truncate title
            content=payload.get("content", "")[:500],  # Truncate content
            url=payload.get("url"),
            score=round(result.score, 4),
            metadata=metadata,
        )
        results.append(search_result)

    # Calculate execution time
    took_ms = (time.time() - start_time) * 1000

    logger.info(
        f"Search completed: {len(results)} results in {took_ms:.2f}ms "
        f"(query='{request.query}')"
    )

    return SearchResponse(
        query=request.query,
        total=len(search_results),  # Total before offset/filtering
        limit=request.limit,
        offset=request.offset,
        results=results,
        took_ms=round(took_ms, 2),
    )


@router.get("/stats", response_model=SearchStatsResponse, status_code=status.HTTP_200_OK)
async def get_search_stats(
    workspace_id: int = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """
    Get search index statistics for the current workspace.

    Returns information about indexed documents, chunks, and sources.

    Args:
        workspace_id: Current workspace ID from auth context
        db: Database session

    Returns:
        SearchStatsResponse with index statistics
    """
    try:
        # Get document counts
        total_docs = (
            db.query(func.count(Document.id))
            .filter(Document.workspace_id == workspace_id)
            .scalar()
        )

        # Get chunk count
        total_chunks = (
            db.query(func.count(DocumentChunk.id))
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.workspace_id == workspace_id)
            .scalar()
        )

        # Get counts by source type
        source_counts = (
            db.query(Document.source_type, func.count(Document.id))
            .filter(Document.workspace_id == workspace_id)
            .group_by(Document.source_type)
            .all()
        )
        sources = {source: count for source, count in source_counts}

        # Get last indexed timestamp
        last_indexed = (
            db.query(func.max(Document.last_indexed_at))
            .filter(Document.workspace_id == workspace_id)
            .scalar()
        )

        # Get Qdrant collection info
        try:
            collection_info = qdrant_client.get_collection(COLLECTION_NAME)
            vector_dimensions = collection_info.config.params.vectors.size
        except Exception as e:
            logger.warning(f"Could not fetch Qdrant collection info: {e}")
            vector_dimensions = 1536  # Default for text-embedding-3-small

        return SearchStatsResponse(
            total_documents=total_docs or 0,
            total_chunks=total_chunks or 0,
            vector_dimensions=vector_dimensions,
            sources=sources,
            last_indexed=last_indexed,
        )

    except Exception as e:
        logger.error(f"Error fetching search stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch search statistics",
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def search_health():
    """
    Check search service health.

    Verifies that OpenAI and Qdrant clients are accessible.

    Returns:
        Health status dictionary
    """
    health = {
        "status": "healthy",
        "openai": "unknown",
        "qdrant": "unknown",
    }

    # Check OpenAI
    try:
        # Simple test - check if client is configured
        if settings.openai_api_key:
            health["openai"] = "configured"
        else:
            health["openai"] = "not_configured"
    except Exception as e:
        logger.warning(f"OpenAI health check failed: {e}")
        health["openai"] = "error"
        health["status"] = "degraded"

    # Check Qdrant
    try:
        collections = qdrant_client.get_collections()
        collection_names = [c.name for c in collections.collections]
        if COLLECTION_NAME in collection_names:
            health["qdrant"] = "ready"
        else:
            health["qdrant"] = "collection_missing"
            health["status"] = "degraded"
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        health["qdrant"] = "error"
        health["status"] = "degraded"

    return health
