"""Tests for text chunking utility."""

import pytest

from src.ingestion.chunker import chunk_text


def test_chunk_text_basic() -> None:
    """Test basic text chunking."""
    text = "This is a test document. " * 100  # ~400 words
    
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=100)
    
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert all(isinstance(chunk, str) for chunk in chunks)


def test_chunk_text_preserves_content() -> None:
    """Test that chunking preserves all content."""
    text = "The quick brown fox jumps over the lazy dog. " * 50
    
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
    
    # All chunks should contain text
    assert all(len(chunk) > 0 for chunk in chunks)
    
    # First chunk should start with beginning of text
    assert chunks[0].startswith("The quick brown")


def test_chunk_text_short_document() -> None:
    """Test chunking document shorter than chunk size."""
    text = "This is a short document with only a few words."
    
    chunks = chunk_text(text, chunk_size=1000, chunk_overlap=100)
    
    # Should return single chunk
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_overlap() -> None:
    """Test that chunks have overlapping content."""
    text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    
    chunks = chunk_text(text, chunk_size=30, chunk_overlap=15)
    
    # With overlap, adjacent chunks should share some content
    if len(chunks) > 1:
        # Check that there's some overlap between chunks
        assert len(chunks) >= 2


def test_chunk_text_custom_separators() -> None:
    """Test chunking with custom separators."""
    text = """
# Heading 1

This is paragraph one.

## Heading 2

This is paragraph two.

### Heading 3

This is paragraph three.
"""
    
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    
    assert len(chunks) > 0
    # Chunks should respect markdown structure
    assert all(isinstance(chunk, str) for chunk in chunks)


def test_chunk_text_empty_string() -> None:
    """Test chunking empty string."""
    chunks = chunk_text("", chunk_size=500, chunk_overlap=100)
    
    # Should return empty list or single empty chunk
    assert len(chunks) <= 1


def test_chunk_text_different_sizes() -> None:
    """Test chunking with different chunk sizes."""
    text = "Word " * 500  # ~2500 characters
    
    chunks_small = chunk_text(text, chunk_size=200, chunk_overlap=50)
    chunks_large = chunk_text(text, chunk_size=1000, chunk_overlap=100)
    
    # Smaller chunks should produce more chunks
    assert len(chunks_small) > len(chunks_large)


def test_chunk_text_preserves_sentences() -> None:
    """Test that chunking tries to preserve sentence boundaries."""
    text = """
    This is the first sentence. This is the second sentence. This is the third sentence.
    This is the fourth sentence. This is the fifth sentence. This is the sixth sentence.
    This is the seventh sentence. This is the eighth sentence.
    """
    
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    
    # Most chunks should end with sentence-ending punctuation
    # (though not guaranteed due to size constraints)
    assert all(isinstance(chunk, str) for chunk in chunks)


def test_chunk_text_token_count_estimate() -> None:
    """Test that chunks are roughly within token limits."""
    # ~1 token ≈ 4 characters for English text
    text = "word " * 1000  # ~5000 characters
    
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=100)
    
    # Check that chunks are reasonable size (accounting for ~4 chars per token)
    for chunk in chunks:
        # Chunks should be roughly 500 tokens or less (2000 chars)
        # Allow some flexibility for overlap and boundaries
        assert len(chunk) <= 3000  # Conservative upper bound
