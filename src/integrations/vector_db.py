"""Vector database client abstraction with pluggable backends."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from qdrant_client import QdrantClient as QdrantClientSDK
from qdrant_client.models import Distance, PointStruct, VectorParams, Filter, FieldCondition, MatchValue

from src.config import settings


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
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: str = "documents",
    ):
        """
        Initialize Qdrant client.
        
        Args:
            url: Qdrant server URL (defaults to settings.qdrant_url)
            api_key: API key for authentication (defaults to settings.qdrant_api_key)
            collection_name: Collection name for storing vectors
        """
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.collection_name = collection_name
        
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
        Search for similar vectors.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Metadata filters (e.g., {"workspace_id": 1})
            
        Returns:
            List of results with id, score, and metadata
        """
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
        
        return [
            {
                "id": str(result.id),
                "score": result.score,
                "metadata": result.payload,
            }
            for result in results
        ]
    
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
