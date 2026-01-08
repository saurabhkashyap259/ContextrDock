"""Vector database client abstraction with pluggable backends."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from datetime import datetime
import logging

from qdrant_client import QdrantClient as QdrantClientSDK
from qdrant_client.models import Distance, PointStruct, VectorParams, Filter, FieldCondition, MatchValue

from src.config import settings

logger = logging.getLogger(__name__)


class CircuitState:
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, use fallback
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for Qdrant vector database (T192).

    Prevents cascading failures by:
    - Opening circuit after 3 consecutive failures
    - Falling back to keyword-only search when open
    - Attempting recovery after timeout period
    """

    def __init__(self, failure_threshold: int = 3, timeout: int = 60):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: Optional[datetime] = None

    def record_success(self):
        """Record successful call, reset failures."""
        self.failures = 0
        self.state = CircuitState.CLOSED
        logger.info("Circuit breaker: recorded success, state=CLOSED")

    def record_failure(self):
        """Record failed call, open circuit if threshold reached."""
        self.failures += 1
        self.last_failure_time = datetime.now()

        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker: opened after {self.failures} failures, "
                "falling back to keyword-only search"
            )

    def can_attempt(self) -> bool:
        """Check if circuit allows attempting call."""
        if self.state == CircuitState.CLOSED:
            return True

        # Check if timeout has passed for OPEN state
        if self.state == CircuitState.OPEN and self.last_failure_time:
            elapsed = (datetime.now() - self.last_failure_time).total_seconds()
            if elapsed >= self.timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker: moving to HALF_OPEN state for recovery attempt")
                return True

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN


class VectorDB(ABC):
    """
    Abstract base class for vector database clients.

    Enables pluggable backends (Qdrant, Weaviate, pgvector) per FR-043.
    """

    @abstractmethod
    def upsert_vector(
        self,
        vector_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """Insert or update a vector with metadata."""
        pass

    @abstractmethod
    def search_vectors(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        pass

    @abstractmethod
    def delete_vector(self, vector_id: str) -> None:
        """Delete a vector by ID."""
        pass

    @abstractmethod
    def ensure_collection(self, vector_size: int = 1536) -> None:
        """Ensure the collection/index exists."""
        pass


class QdrantClient(VectorDB):
    """
    Qdrant vector database client implementation.

    Qdrant is optimized for:
    - Fast vector similarity search
    - Advanced filtering with metadata
    - Horizontal scalability

    Includes circuit breaker pattern (T192) for fault tolerance.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: str = "documents",
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        """
        Initialize Qdrant client.

        Args:
            url: Qdrant server URL (defaults to settings.qdrant_url)
            api_key: API key for authentication (defaults to settings.qdrant_api_key)
            collection_name: Collection name for storing vectors
            circuit_breaker: Optional circuit breaker instance (creates default if None)
        """
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.collection_name = collection_name
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3,
            timeout=60
        )

        self.client = QdrantClientSDK(
            url=self.url,
            api_key=self.api_key if self.api_key else None,
        )

    def ensure_collection(self, vector_size: int = 1536) -> None:
        """
        Create collection if it doesn't exist.

        Args:
            vector_size: Dimension of embedding vectors (1536 for text-embedding-3-small)
        """
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert_vector(
        self,
        vector_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
    ) -> str:
        """
        Insert or update a vector in Qdrant.

        Args:
            vector_id: Unique identifier for the vector
            embedding: Vector embedding
            metadata: Metadata to store with vector

        Returns:
            Vector ID
        """
        point = PointStruct(
            id=vector_id,
            vector=embedding,
            payload=metadata,
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

        return vector_id

    def batch_upsert(self, vectors: List[Tuple[str, List[float], Dict[str, Any]]]) -> None:
        """
        Batch insert/update multiple vectors.

        Args:
            vectors: List of (vector_id, embedding, metadata) tuples
        """
        points = [
            PointStruct(id=vid, vector=emb, payload=meta)
            for vid, emb, meta in vectors
        ]

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def search_vectors(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors with circuit breaker protection (T192).

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Metadata filters (e.g., {"workspace_id": 1})

        Returns:
            List of results with id, score, and metadata

        Note:
            If circuit breaker is open (after 3 failures), returns empty list.
            The caller should fall back to keyword-only search via PostgreSQL.
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                "Circuit breaker is OPEN, skipping Qdrant search. "
                "Use keyword-only search fallback."
            )
            return []

        try:
            # Build filter conditions
            query_filter = None
            if filters:
                conditions = [
                    FieldCondition(key=key, match=MatchValue(value=value))
                    for key, value in filters.items()
                ]
                query_filter = Filter(must=conditions)

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter,
            )

            # Record success
            self.circuit_breaker.record_success()

            return [
                {
                    "id": str(result.id),
                    "score": result.score,
                    "metadata": result.payload,
                }
                for result in results
            ]

        except Exception as e:
            # Record failure
            self.circuit_breaker.record_failure()
            logger.error(
                f"Qdrant search failed: {e}, "
                f"failures={self.circuit_breaker.failures}/{self.circuit_breaker.failure_threshold}"
            )

            # Return empty list, caller should use keyword fallback
            return []

    def delete_vector(self, vector_id: str) -> None:
        """Delete a vector by ID."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[vector_id],
        )

    def delete_by_filter(self, filters: Dict[str, Any]) -> None:
        """
        Delete vectors matching filter criteria.

        Args:
            filters: Metadata filters (e.g., {"document_id": 123})
        """
        conditions = [
            FieldCondition(key=key, match=MatchValue(value=value))
            for key, value in filters.items()
        ]

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(must=conditions),
        )
