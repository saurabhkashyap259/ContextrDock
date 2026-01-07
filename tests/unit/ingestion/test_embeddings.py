"""Tests for embedding service."""

import pytest
from unittest.mock import Mock, patch

from src.ingestion.embeddings import EmbeddingService, get_token_count


def test_embedding_service_initialization() -> None:
    """Test creating an embedding service."""
    service = EmbeddingService(model="text-embedding-3-small")
    
    assert service.model == "text-embedding-3-small"


def test_get_token_count() -> None:
    """Test token counting."""
    text = "This is a test sentence."
    
    token_count = get_token_count(text)
    
    assert isinstance(token_count, int)
    assert token_count > 0
    # Roughly 5-6 tokens for this sentence
    assert 3 < token_count < 10


def test_get_token_count_empty() -> None:
    """Test token counting for empty string."""
    token_count = get_token_count("")
    
    assert token_count == 0


@patch("openai.OpenAI")
def test_embed_text_single(mock_openai_class) -> None:
    """Test embedding a single text."""
    # Mock OpenAI client
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3])]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client
    
    service = EmbeddingService()
    text = "Test document content"
    
    embedding = service.embed_text(text)
    
    assert isinstance(embedding, list)
    assert len(embedding) == 3
    assert all(isinstance(x, float) for x in embedding)
    mock_client.embeddings.create.assert_called_once()


@patch("openai.OpenAI")
def test_embed_texts_batch(mock_openai_class) -> None:
    """Test embedding multiple texts in batch."""
    # Mock OpenAI client
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1, 0.2, 0.3]),
        Mock(embedding=[0.4, 0.5, 0.6]),
        Mock(embedding=[0.7, 0.8, 0.9]),
    ]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client
    
    service = EmbeddingService()
    texts = ["Text one", "Text two", "Text three"]
    
    embeddings = service.embed_texts(texts)
    
    assert isinstance(embeddings, list)
    assert len(embeddings) == 3
    assert all(isinstance(emb, list) for emb in embeddings)
    assert all(len(emb) == 3 for emb in embeddings)
    mock_client.embeddings.create.assert_called_once()


@patch("openai.OpenAI")
def test_embed_text_with_different_model(mock_openai_class) -> None:
    """Test embedding with a different model."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1] * 1536)]  # ada-002 has 1536 dimensions
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client
    
    service = EmbeddingService(model="text-embedding-ada-002")
    text = "Test content"
    
    embedding = service.embed_text(text)
    
    assert len(embedding) == 1536
    call_args = mock_client.embeddings.create.call_args
    assert call_args[1]["model"] == "text-embedding-ada-002"


def test_get_token_count_long_text() -> None:
    """Test token counting for longer text."""
    text = "This is a longer test document. " * 100  # ~600 tokens
    
    token_count = get_token_count(text)
    
    assert 500 < token_count < 800


@patch("openai.OpenAI")
def test_embed_texts_empty_list(mock_openai_class) -> None:
    """Test embedding empty list."""
    service = EmbeddingService()
    
    embeddings = service.embed_texts([])
    
    assert embeddings == []


@patch("openai.OpenAI")
def test_embed_text_handles_api_key_from_settings(mock_openai_class) -> None:
    """Test that service uses API key from settings."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1, 0.2])]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client
    
    service = EmbeddingService()
    service.embed_text("test")
    
    # Verify OpenAI client was initialized
    mock_openai_class.assert_called_once()
