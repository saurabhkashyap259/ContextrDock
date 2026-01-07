"""Tests for vector database client abstraction."""

import pytest
from typing import Dict, List, Any
from unittest.mock import Mock, patch

from src.integrations.vector_db import VectorDB, QdrantClient


def test_vector_db_abstract_class() -> None:
    """Test that VectorDB is abstract."""
    with pytest.raises(TypeError):
        VectorDB()  # Cannot instantiate abstract class


@patch("qdrant_client.QdrantClient")
def test_qdrant_client_initialization(mock_qdrant) -> None:
    """Test QdrantClient initialization."""
    client = QdrantClient(url="http://localhost:6333")
    
    assert client.url == "http://localhost:6333"
    assert client.collection_name == "documents"


@patch("qdrant_client.QdrantClient")
def test_qdrant_upsert_vector(mock_qdrant_class) -> None:
    """Test upserting a vector to Qdrant."""
    mock_client_instance = Mock()
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    
    vector_id = "test-uuid-123"
    embedding = [0.1, 0.2, 0.3]
    metadata = {"document_id": 1, "chunk_index": 0, "workspace_id": 1}
    
    result_id = client.upsert_vector(vector_id, embedding, metadata)
    
    assert result_id == vector_id
    mock_client_instance.upsert.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_qdrant_search_vectors(mock_qdrant_class) -> None:
    """Test searching vectors in Qdrant."""
    mock_client_instance = Mock()
    mock_result = Mock()
    mock_result.id = "uuid-1"
    mock_result.score = 0.95
    mock_result.payload = {"document_id": 1, "content": "Test"}
    mock_client_instance.search.return_value = [mock_result]
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    
    query_embedding = [0.1, 0.2, 0.3]
    filters = {"workspace_id": 1}
    
    results = client.search_vectors(query_embedding, top_k=5, filters=filters)
    
    assert len(results) == 1
    assert results[0]["id"] == "uuid-1"
    assert results[0]["score"] == 0.95
    assert results[0]["metadata"]["document_id"] == 1


@patch("qdrant_client.QdrantClient")
def test_qdrant_delete_vector(mock_qdrant_class) -> None:
    """Test deleting a vector from Qdrant."""
    mock_client_instance = Mock()
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    vector_id = "test-uuid-456"
    
    client.delete_vector(vector_id)
    
    mock_client_instance.delete.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_qdrant_ensure_collection(mock_qdrant_class) -> None:
    """Test ensuring collection exists."""
    mock_client_instance = Mock()
    mock_client_instance.collection_exists.return_value = False
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    client.ensure_collection(vector_size=1536)
    
    mock_client_instance.collection_exists.assert_called_once()
    mock_client_instance.create_collection.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_qdrant_search_with_no_filters(mock_qdrant_class) -> None:
    """Test searching without filters."""
    mock_client_instance = Mock()
    mock_client_instance.search.return_value = []
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    query_embedding = [0.1] * 1536
    
    results = client.search_vectors(query_embedding, top_k=10)
    
    assert results == []
    mock_client_instance.search.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_qdrant_batch_upsert(mock_qdrant_class) -> None:
    """Test batch upserting multiple vectors."""
    mock_client_instance = Mock()
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    
    vectors = [
        ("id-1", [0.1, 0.2], {"doc_id": 1}),
        ("id-2", [0.3, 0.4], {"doc_id": 2}),
    ]
    
    client.batch_upsert(vectors)
    
    mock_client_instance.upsert.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_qdrant_delete_by_filter(mock_qdrant_class) -> None:
    """Test deleting vectors by filter."""
    mock_client_instance = Mock()
    mock_qdrant_class.return_value = mock_client_instance
    
    client = QdrantClient()
    filters = {"document_id": 123}
    
    client.delete_by_filter(filters)
    
    mock_client_instance.delete.assert_called_once()
