"""Hybrid search combining BM25 keyword search and vector similarity with RRF."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.retrieval.keyword_search import search_by_keywords
from src.retrieval.vector_search import search_by_vector
from src.services.acl_validator import ACLValidator

logger = logging.getLogger(__name__)


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
    user: Optional[Dict[str, Any]] = None,
    top_k: int = 10,
    keyword_weight: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining keyword (BM25) and vector similarity search.
    
    Uses Reciprocal Rank Fusion to merge results from both methods.
    This provides:
    - Lexical matching (keyword search) for exact terms
    - Semantic matching (vector search) for meaning/intent
    - Permission-aware filtering (ACL validation)
    
    Args:
        db_session: Database session
        query: Search query
        workspace_id: Workspace ID for filtering
        user: User object with connector_identities for ACL filtering (optional)
        top_k: Maximum number of results to return
        keyword_weight: Weight for keyword vs vector (not used in RRF, kept for API compatibility)
        
    Returns:
        Merged, ranked, and ACL-filtered search results
        
    Example:
        >>> results = hybrid_search(
        ...     db_session=session,
        ...     query="OAuth authentication",
        ...     workspace_id=1,
        ...     user={"id": 1, "connector_identities": {...}},
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
    
    # Apply ACL filtering if user provided
    if user:
        filtered_results = apply_acl_filtering(user, merged_results)
        logger.info(
            f"ACL filtering: {len(merged_results)} results -> {len(filtered_results)} "
            f"allowed for user {user.get('id')}"
        )
    else:
        filtered_results = merged_results
        logger.warning("No user provided, skipping ACL filtering")
    
    # Return top K results after ACL filtering
    return filtered_results[:top_k]


def apply_acl_filtering(
    user: Dict[str, Any],
    results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Filter search results based on user permissions.
    
    Uses ACLValidator to check if user has access to each result chunk.
    Implements fail-closed security: if ACL check fails, result is excluded.
    
    Args:
        user: User object with connector_identities
        results: List of search results with acl_json field
        
    Returns:
        Filtered list containing only results user can access
    """
    if not user:
        logger.warning("No user provided to apply_acl_filtering, returning empty list")
        return []
    
    acl_validator = ACLValidator()
    filtered_results = []
    
    denied_count = 0
    undefined_count = 0
    
    for result in results:
        acl_metadata = result.get("acl_json")
        
        # Track undefined ACLs for logging
        if acl_metadata is None:
            undefined_count += 1
        
        # Check access
        acl_result = acl_validator.check_access(user, acl_metadata)
        
        if acl_result.allowed:
            filtered_results.append(result)
        else:
            denied_count += 1
            logger.debug(
                f"Access denied to chunk {result.get('chunk_id')}: {acl_result.reason}"
            )
    
    # Log filtering summary
    logger.info(
        f"ACL filtering summary: {len(filtered_results)} allowed, "
        f"{denied_count} denied, {undefined_count} undefined ACLs"
    )
    
    return filtered_results
