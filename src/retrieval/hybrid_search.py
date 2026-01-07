"""Hybrid search combining BM25 keyword search and vector similarity with RRF."""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from src.retrieval.keyword_search import search_by_keywords
from src.retrieval.vector_search import search_by_vector


def reciprocal_rank_fusion(
    list1: List[Dict[str, Any]],
    list2: List[Dict[str, Any]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion (RRF).
    
    RRF formula: score = sum(1 / (k + rank_i))
    where rank_i is the position in result list i (1-indexed)
    
    This gives higher scores to items that appear in multiple lists
    and rank high in those lists.
    
    Args:
        list1: First ranked list (e.g., keyword search results)
        list2: Second ranked list (e.g., vector search results)
        k: Constant to reduce impact of high ranks (default: 60)
        
    Returns:
        Merged and re-ranked list
        
    Reference:
        Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009).
        Reciprocal rank fusion outperforms condorcet and individual rank learning methods.
    """
    # Build RRF scores
    rrf_scores: Dict[int, float] = {}
    items_dict: Dict[int, Dict[str, Any]] = {}
    
    # Process first list
    for rank, item in enumerate(list1, start=1):
        chunk_id = item["chunk_id"]
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        if chunk_id not in items_dict:
            items_dict[chunk_id] = item.copy()
    
    # Process second list
    for rank, item in enumerate(list2, start=1):
        chunk_id = item["chunk_id"]
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        if chunk_id not in items_dict:
            items_dict[chunk_id] = item.copy()
    
    # Create merged results with RRF scores
    merged_results = []
    for chunk_id, score in rrf_scores.items():
        item = items_dict[chunk_id].copy()
        item["score"] = score
        merged_results.append(item)
    
    # Sort by RRF score (descending)
    merged_results.sort(key=lambda x: x["score"], reverse=True)
    
    return merged_results


def hybrid_search(
    db_session: Session,
    query: str,
    workspace_id: int,
    top_k: int = 10,
    keyword_weight: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining keyword (BM25) and vector similarity search.
    
    Uses Reciprocal Rank Fusion to merge results from both methods.
    This provides:
    - Lexical matching (keyword search) for exact terms
    - Semantic matching (vector search) for meaning/intent
    
    Args:
        db_session: Database session
        query: Search query
        workspace_id: Workspace ID for filtering
        top_k: Maximum number of results to return
        keyword_weight: Weight for keyword vs vector (not used in RRF, kept for API compatibility)
        
    Returns:
        Merged and ranked search results
        
    Example:
        >>> results = hybrid_search(
        ...     db_session=session,
        ...     query="OAuth authentication",
        ...     workspace_id=1,
        ...     top_k=5,
        ... )
        >>> results[0]["title"]
        'API Authentication Guide'
    """
    if not query or not query.strip():
        return []
    
    # Perform both searches (retrieve more results for better merging)
    retrieval_k = top_k * 3  # Retrieve 3x results from each method
    
    keyword_results = search_by_keywords(
        db_session=db_session,
        query=query,
        workspace_id=workspace_id,
        top_k=retrieval_k,
    )
    
    vector_results = search_by_vector(
        db_session=db_session,
        query=query,
        workspace_id=workspace_id,
        top_k=retrieval_k,
    )
    
    # Merge using Reciprocal Rank Fusion
    merged_results = reciprocal_rank_fusion(keyword_results, vector_results, k=60)
    
    # Return top K results
    return merged_results[:top_k]
