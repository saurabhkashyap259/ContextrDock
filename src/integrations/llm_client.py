"""Abstract LLM client with OpenAI, Anthropic, and Ollama implementations."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, Optional

import requests


class LLMClient(ABC):
    """
    Abstract base class for LLM integrations.

    Provides a unified interface for different LLM providers (OpenAI, Anthropic, Ollama).
    Enables pluggable backends per FR-042 (Pluggable AI backends).
    """

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate a completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            Dict with 'content' and 'usage' keys
        """
        pass

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """
        Stream completion chunks.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Yields:
            Content chunks as they are generated
        """
        pass


class OpenAIClient(LLMClient):
    """OpenAI LLM client (GPT-4, GPT-3.5, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4", **kwargs: Any):
        """
        Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model name (gpt-4, gpt-3.5-turbo, etc.)
            **kwargs: Additional OpenAI client parameters
        """
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, **kwargs)
        self.model = model
        self.api_key = api_key

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate completion using OpenAI API."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return {
            "content": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream completion using OpenAI API."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class AnthropicClient(LLMClient):
    """Anthropic LLM client (Claude 3, etc.)."""

    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229", **kwargs: Any):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key
            model: Model name (claude-3-opus, claude-3-sonnet, etc.)
            **kwargs: Additional Anthropic client parameters
        """
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key, **kwargs)
        self.model = model
        self.api_key = api_key

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate completion using Anthropic API."""
        # Anthropic requires system message separately
        system_message = None
        filtered_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        request_params = {
            "model": self.model,
            "messages": filtered_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,  # Anthropic requires max_tokens
            **kwargs,
        }

        if system_message:
            request_params["system"] = system_message

        response = self.client.messages.create(**request_params)

        return {
            "content": response.content[0].text,
            "usage": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
        }

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream completion using Anthropic API."""
        # Extract system message
        system_message = None
        filtered_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        request_params = {
            "model": self.model,
            "messages": filtered_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
            "stream": True,
            **kwargs,
        }

        if system_message:
            request_params["system"] = system_message

        with self.client.messages.stream(**request_params) as stream:
            for text in stream.text_stream:
                yield text


class OllamaClient(LLMClient):
    """Ollama LLM client (local models)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2", **kwargs: Any):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama server URL
            model: Model name (llama2, mistral, etc.)
            **kwargs: Additional parameters
        """
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate completion using Ollama API."""
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
            **kwargs,
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data["message"]["content"],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream completion using Ollama API."""
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
            **kwargs,
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()

        import json
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "message" in data and "content" in data["message"]:
                    yield data["message"]["content"]
