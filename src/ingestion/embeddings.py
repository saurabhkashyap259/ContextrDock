"""Embedding service for generating text embeddings using OpenAI."""

from typing import List

import tiktoken
from openai import OpenAI

from src.config import settings


def get_token_count(text: str, model: str = "cl100k_base") -> int:
    """
    Count tokens in text using tiktoken.
    
    Args:
        text: Input text
        model: Encoding model (cl100k_base for GPT-4, text-embedding-3-*)
        
    Returns:
        Number of tokens
    """
    if not text:
        return 0
    
    encoding = tiktoken.get_encoding(model)
    tokens = encoding.encode(text)
    return len(tokens)


class EmbeddingService:
    """
    Service for generating embeddings using OpenAI's embedding models.
    
    Supports:
    - text-embedding-3-small (1536 dimensions, cost-effective)
    - text-embedding-3-large (3072 dimensions, higher quality)
    - text-embedding-ada-002 (1536 dimensions, legacy)
    """
    
    def __init__(self, model: str = "text-embedding-3-small"):
        """
        Initialize embedding service.
        
        Args:
            model: OpenAI embedding model name
        """
        self.model = model
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            Embedding vector (list of floats)
            
        Example:
            >>> service = EmbeddingService()
            >>> embedding = service.embed_text("Hello world")
            >>> len(embedding)
            1536
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        
        return response.data[0].embedding
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        More efficient than calling embed_text() multiple times.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Example:
            >>> service = EmbeddingService()
            >>> embeddings = service.embed_texts(["Text 1", "Text 2"])
            >>> len(embeddings)
            2
        """
        if not texts:
            return []
        
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        
        return [item.embedding for item in response.data]
