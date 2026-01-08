"""Embedding service for generating text embeddings using OpenAI."""

import logging
import random

import tiktoken
from openai import OpenAI

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingRetryManager:
    """
    Manager for embedding API retry logic with exponential backoff and jitter (T196).

    Features:
    - Exponential backoff: 1s, 2s, 4s, 8s
    - Random jitter (±25%) to prevent thundering herd
    - Automatic retry on rate limits and transient errors
    """

    def __init__(self):
        self.base_delays = [1, 2, 4, 8]  # Base delays in seconds
        self.jitter_range = 0.25  # ±25% jitter

    def get_delay_with_jitter(self, base_delay: float) -> float:
        """
        Add random jitter to base delay to prevent thundering herd.

        Args:
            base_delay: Base delay in seconds

        Returns:
            Delay with jitter applied (±25%)
        """
        jitter = random.uniform(-self.jitter_range, self.jitter_range)
        return base_delay * (1 + jitter)

    def call_with_retry(self, func: callable, *args, **kwargs):
        """
        Call function with retry logic (synchronous).

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If all retries fail
        """
        last_exception = None

        for attempt, base_delay in enumerate(self.base_delays):
            try:
                result = func(*args, **kwargs)

                # Log successful retry if not first attempt
                if attempt > 0:
                    logger.info(
                        f"Embedding API call succeeded on attempt {attempt + 1}"
                    )

                return result

            except Exception as e:
                last_exception = e

                logger.warning(
                    f"Embedding API call failed (attempt {attempt + 1}/{len(self.base_delays)}): {e}"
                )

                # Check if we should retry
                if attempt < len(self.base_delays) - 1:
                    # Apply jitter to delay
                    delay = self.get_delay_with_jitter(base_delay)

                    logger.info(f"Retrying in {delay:.2f}s...")

                    # Wait before retry
                    import time
                    time.sleep(delay)
                else:
                    # Final attempt failed
                    logger.error(
                        f"Embedding API call failed after {len(self.base_delays)} attempts"
                    )
                    raise

        # Should not reach here, but raise last exception if we do
        raise last_exception


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

    Includes retry logic with exponential backoff and jitter (T196).
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        """
        Initialize embedding service.

        Args:
            model: OpenAI embedding model name
        """
        self.model = model
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.retry_manager = EmbeddingRetryManager()

    def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text with retry logic (T196).

        Args:
            text: Input text to embed

        Returns:
            Embedding vector (list of floats)

        Raises:
            Exception: If embedding fails after all retries (1s, 2s, 4s, 8s)

        Example:
            >>> service = EmbeddingService()
            >>> embedding = service.embed_text("Hello world")
            >>> len(embedding)
            1536
        """
        def _embed():
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding

        return self.retry_manager.call_with_retry(_embed)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in batch with retry logic (T196).

        More efficient than calling embed_text() multiple times.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            Exception: If embedding fails after all retries (1s, 2s, 4s, 8s)

        Example:
            >>> service = EmbeddingService()
            >>> embeddings = service.embed_texts(["Text 1", "Text 2"])
            >>> len(embeddings)
            2
        """
        if not texts:
            return []

        def _embed():
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            return [item.embedding for item in response.data]

        return self.retry_manager.call_with_retry(_embed)
