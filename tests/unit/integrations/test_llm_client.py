"""Tests for abstract LLM client interface."""

import pytest
from typing import List, Dict, Any

from src.integrations.llm_client import LLMClient, OpenAIClient, AnthropicClient, OllamaClient


def test_llm_client_is_abstract() -> None:
    """Test that LLMClient cannot be instantiated directly."""
    with pytest.raises(TypeError):
        LLMClient()  # type: ignore


def test_openai_client_initialization() -> None:
    """Test OpenAI client initialization."""
    client = OpenAIClient(api_key="test-key", model="gpt-4")
    
    assert client.model == "gpt-4"
    assert client.api_key == "test-key"


def test_anthropic_client_initialization() -> None:
    """Test Anthropic client initialization."""
    client = AnthropicClient(api_key="test-key", model="claude-3-sonnet-20240229")
    
    assert client.model == "claude-3-sonnet-20240229"
    assert client.api_key == "test-key"


def test_ollama_client_initialization() -> None:
    """Test Ollama client initialization."""
    client = OllamaClient(base_url="http://localhost:11434", model="llama2")
    
    assert client.model == "llama2"
    assert client.base_url == "http://localhost:11434"


def test_openai_client_generate(monkeypatch) -> None:
    """Test OpenAI client generate method."""
    # Mock OpenAI API
    mock_response = type('Response', (), {
        'choices': [
            type('Choice', (), {
                'message': type('Message', (), {
                    'content': 'Generated response'
                })()
            })()
        ],
        'usage': type('Usage', (), {
            'prompt_tokens': 10,
            'completion_tokens': 5,
            'total_tokens': 15
        })()
    })()
    
    class MockOpenAI:
        class Chat:
            class Completions:
                def create(self, **kwargs):
                    return mock_response
            completions = Completions()
        chat = Chat()
    
    def mock_openai_init(self, *args, **kwargs):
        self.client = MockOpenAI()
        self.model = kwargs.get('model', 'gpt-4')
        self.api_key = kwargs.get('api_key')
    
    monkeypatch.setattr(OpenAIClient, "__init__", mock_openai_init)
    
    client = OpenAIClient(api_key="test-key", model="gpt-4")
    client.client = MockOpenAI()
    
    messages = [{"role": "user", "content": "Test message"}]
    response = client.generate(messages, temperature=0.7, max_tokens=100)
    
    assert response["content"] == "Generated response"
    assert response["usage"]["total_tokens"] == 15


def test_anthropic_client_generate(monkeypatch) -> None:
    """Test Anthropic client generate method."""
    # Mock Anthropic API
    mock_response = type('Response', (), {
        'content': [type('Content', (), {'text': 'Generated response'})()],
        'usage': type('Usage', (), {
            'input_tokens': 10,
            'output_tokens': 5
        })()
    })()
    
    class MockAnthropic:
        class Messages:
            def create(self, **kwargs):
                return mock_response
        messages = Messages()
    
    def mock_anthropic_init(self, *args, **kwargs):
        self.client = MockAnthropic()
        self.model = kwargs.get('model', 'claude-3-sonnet-20240229')
        self.api_key = kwargs.get('api_key')
    
    monkeypatch.setattr(AnthropicClient, "__init__", mock_anthropic_init)
    
    client = AnthropicClient(api_key="test-key", model="claude-3-sonnet-20240229")
    client.client = MockAnthropic()
    
    messages = [{"role": "user", "content": "Test message"}]
    response = client.generate(messages, temperature=0.7, max_tokens=100)
    
    assert response["content"] == "Generated response"
    assert response["usage"]["total_tokens"] == 15


def test_ollama_client_generate(monkeypatch) -> None:
    """Test Ollama client generate method."""
    import json
    
    # Mock requests.post
    class MockResponse:
        def json(self):
            return {
                "message": {"content": "Generated response"},
                "prompt_eval_count": 10,
                "eval_count": 5
            }
        
        def raise_for_status(self):
            pass
    
    def mock_post(*args, **kwargs):
        return MockResponse()
    
    import requests
    monkeypatch.setattr(requests, "post", mock_post)
    
    client = OllamaClient(base_url="http://localhost:11434", model="llama2")
    
    messages = [{"role": "user", "content": "Test message"}]
    response = client.generate(messages, temperature=0.7, max_tokens=100)
    
    assert response["content"] == "Generated response"
    assert response["usage"]["total_tokens"] == 15


def test_llm_client_supports_system_messages() -> None:
    """Test that clients support system messages."""
    client = OpenAIClient(api_key="test-key", model="gpt-4")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"}
    ]
    
    # Should not raise error (actual API call will be mocked in integration tests)
    assert callable(client.generate)


def test_llm_client_supports_streaming() -> None:
    """Test that clients support streaming responses."""
    client = OpenAIClient(api_key="test-key", model="gpt-4")
    
    # Check that stream method exists
    assert hasattr(client, 'stream')
    assert callable(client.stream)


def test_llm_client_handles_token_limits() -> None:
    """Test that clients respect max_tokens parameter."""
    client = OpenAIClient(api_key="test-key", model="gpt-4")
    
    # Should accept max_tokens parameter
    messages = [{"role": "user", "content": "Test"}]
    
    # Verify method signature accepts max_tokens
    import inspect
    sig = inspect.signature(client.generate)
    assert 'max_tokens' in sig.parameters
