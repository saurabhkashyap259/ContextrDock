"""Tests for rate limiter decorator."""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

from src.connectors.sdk.rate_limiter import (
    RateLimiter,
    rate_limit,
    RateLimitExceeded,
    TokenBucket
)


def test_token_bucket_creation():
    """Test TokenBucket creation with capacity and refill rate."""
    bucket = TokenBucket(capacity=100, refill_rate=10)
    
    assert bucket.capacity == 100
    assert bucket.refill_rate == 10
    assert bucket.tokens == 100  # Starts full


def test_token_bucket_consume():
    """Test consuming tokens from bucket."""
    bucket = TokenBucket(capacity=10, refill_rate=1)
    
    # Consume 3 tokens
    assert bucket.consume(3) is True
    assert abs(bucket.tokens - 7) < 0.1  # Allow small timing variance
    
    # Consume 5 more
    assert bucket.consume(5) is True
    assert abs(bucket.tokens - 2) < 0.1  # Allow small timing variance


def test_token_bucket_consume_more_than_available():
    """Test consuming more tokens than available."""
    bucket = TokenBucket(capacity=10, refill_rate=1)
    
    # Try to consume more than available
    assert bucket.consume(15) is False
    assert bucket.tokens == 10  # Tokens unchanged


def test_token_bucket_refill():
    """Test token refill over time."""
    bucket = TokenBucket(capacity=10, refill_rate=5)  # 5 tokens per second
    
    # Consume all tokens
    bucket.consume(10)
    assert bucket.tokens == 0
    
    # Wait 1 second and refill
    time.sleep(1.1)
    bucket._refill()
    
    # Should have ~5 tokens back (5 per second * 1 second)
    assert bucket.tokens >= 4  # Allow for timing variance
    assert bucket.tokens <= 6


def test_token_bucket_max_capacity():
    """Test that tokens don't exceed capacity after refill."""
    bucket = TokenBucket(capacity=10, refill_rate=10)
    
    # Wait and refill (shouldn't exceed capacity)
    time.sleep(2)
    bucket._refill()
    
    assert bucket.tokens == 10  # Capped at capacity


def test_rate_limiter_initialization():
    """Test RateLimiter initialization."""
    limiter = RateLimiter(calls=100, period=60)
    
    assert limiter.calls == 100
    assert limiter.period == 60
    assert isinstance(limiter.bucket, TokenBucket)


def test_rate_limiter_allow():
    """Test allowing requests within rate limit."""
    limiter = RateLimiter(calls=10, period=60)
    
    # First 10 calls should be allowed
    for _ in range(10):
        assert limiter.allow() is True


def test_rate_limiter_block():
    """Test blocking requests over rate limit."""
    limiter = RateLimiter(calls=5, period=60)
    
    # Consume all tokens
    for _ in range(5):
        assert limiter.allow() is True
    
    # Next call should be blocked
    assert limiter.allow() is False


def test_rate_limiter_wait():
    """Test waiting for rate limit to reset."""
    limiter = RateLimiter(calls=5, period=1)  # 5 calls per second
    
    # Consume all tokens
    for _ in range(5):
        limiter.allow()
    
    # Wait should unblock after ~1 second
    wait_time = limiter.wait()
    assert wait_time > 0
    assert wait_time <= 1.0


def test_rate_limit_decorator_allows_calls():
    """Test rate_limit decorator allows calls within limit."""
    @rate_limit(calls=10, period=60)
    def api_call():
        return "success"
    
    # Should succeed
    result = api_call()
    assert result == "success"


def test_rate_limit_decorator_blocks_excess_calls():
    """Test rate_limit decorator blocks calls over limit."""
    call_count = 0
    
    @rate_limit(calls=3, period=60)
    def api_call():
        nonlocal call_count
        call_count += 1
        return f"call {call_count}"
    
    # First 3 calls succeed
    api_call()
    api_call()
    api_call()
    
    # 4th call should raise RateLimitExceeded
    with pytest.raises(RateLimitExceeded):
        api_call()


def test_rate_limit_decorator_with_auto_retry():
    """Test rate_limit decorator with auto_retry."""
    call_count = 0
    
    @rate_limit(calls=5, period=1, auto_retry=True)
    def api_call():
        nonlocal call_count
        call_count += 1
        return f"call {call_count}"
    
    # Consume all tokens
    for _ in range(5):
        api_call()
    
    # Next call should wait and retry
    start = time.time()
    result = api_call()
    elapsed = time.time() - start
    
    assert result == "call 6"
    assert elapsed >= 0.2  # Should have waited


def test_rate_limit_decorator_preserves_function_metadata():
    """Test that decorator preserves function name and docstring."""
    @rate_limit(calls=10, period=60)
    def my_function():
        """My docstring."""
        pass
    
    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "My docstring."


def test_rate_limit_decorator_with_arguments():
    """Test rate_limit decorator on function with arguments."""
    @rate_limit(calls=10, period=60)
    def api_call(user_id: int, action: str):
        return f"User {user_id}: {action}"
    
    result = api_call(123, "login")
    assert result == "User 123: login"


def test_rate_limit_decorator_with_method():
    """Test rate_limit decorator on class method."""
    class APIClient:
        @rate_limit(calls=5, period=60)
        def fetch_data(self, resource: str):
            return f"Fetching {resource}"
    
    client = APIClient()
    result = client.fetch_data("users")
    assert result == "Fetching users"


def test_rate_limit_exception_message():
    """Test RateLimitExceeded exception message."""
    exc = RateLimitExceeded(retry_after=30)
    
    assert "Rate limit exceeded" in str(exc)
    assert "30" in str(exc)


def test_rate_limit_exception_retry_after():
    """Test RateLimitExceeded exception retry_after attribute."""
    exc = RateLimitExceeded(retry_after=45)
    
    assert exc.retry_after == 45


@patch('time.sleep')
def test_rate_limit_with_backoff_on_429(mock_sleep):
    """Test rate_limit handles 429 responses with exponential backoff."""
    call_count = 0
    
    @rate_limit(calls=10, period=60, handle_429=True, max_retries=3)
    def api_call():
        nonlocal call_count
        call_count += 1
        
        if call_count <= 2:
            # Simulate 429 response
            class Response429:
                status_code = 429
                headers = {"Retry-After": "2"}
            
            from requests.exceptions import HTTPError
            response = Response429()
            raise HTTPError(response=response)
        
        return "success"
    
    # Should retry and eventually succeed
    result = api_call()
    
    assert result == "success"
    assert call_count == 3  # 2 failures + 1 success
    assert mock_sleep.call_count >= 2  # Should have slept for retries


def test_multiple_rate_limiters_independent():
    """Test that multiple rate limiters are independent."""
    @rate_limit(calls=5, period=60)
    def api_1():
        return "api1"
    
    @rate_limit(calls=3, period=60)
    def api_2():
        return "api2"
    
    # Consume api_1 limit
    for _ in range(5):
        api_1()
    
    # api_2 should still work (independent limiter)
    result = api_2()
    assert result == "api2"


def test_rate_limiter_reset():
    """Test rate limiter can be manually reset."""
    limiter = RateLimiter(calls=5, period=60)
    
    # Consume all tokens
    for _ in range(5):
        limiter.allow()
    
    # Should be blocked
    assert limiter.allow() is False
    
    # Reset
    limiter.reset()
    
    # Should be allowed again
    assert limiter.allow() is True


def test_rate_limiter_get_stats():
    """Test getting rate limiter statistics."""
    limiter = RateLimiter(calls=10, period=60)
    
    # Consume 3 tokens
    for _ in range(3):
        limiter.allow()
    
    stats = limiter.get_stats()
    
    assert stats["capacity"] == 10
    assert stats["remaining"] >= 6  # Should have ~7 remaining
    assert stats["remaining"] <= 8
    assert "reset_at" in stats
