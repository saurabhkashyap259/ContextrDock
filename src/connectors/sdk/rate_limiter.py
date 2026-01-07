"""Rate limiter for connector API calls."""

import time
import functools
from datetime import datetime, timezone
from typing import Callable, Any, Dict
from threading import Lock


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, retry_after: float):
        """
        Initialize exception.
        
        Args:
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds.")


class TokenBucket:
    """
    Token bucket algorithm for rate limiting.
    
    Tokens are added at a constant rate (refill_rate per second).
    Each request consumes one or more tokens.
    Requests are blocked when bucket is empty.
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens (burst capacity)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = Lock()
    
    def _refill(self) -> None:
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume
        
        Returns:
            True if tokens consumed, False if not enough tokens
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def wait_time(self) -> float:
        """
        Calculate time to wait for tokens to be available.
        
        Returns:
            Seconds to wait for at least 1 token
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= 1:
                return 0.0
            
            tokens_needed = 1 - self.tokens
            return tokens_needed / self.refill_rate


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.
    
    Example:
        limiter = RateLimiter(calls=100, period=60)  # 100 calls per minute
        
        if limiter.allow():
            make_api_call()
        else:
            wait_time = limiter.wait()
            time.sleep(wait_time)
    """
    
    def __init__(self, calls: int, period: float):
        """
        Initialize rate limiter.
        
        Args:
            calls: Maximum number of calls
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self.bucket = TokenBucket(
            capacity=calls,
            refill_rate=calls / period
        )
    
    def allow(self) -> bool:
        """
        Check if request is allowed.
        
        Returns:
            True if request allowed, False if rate limit exceeded
        """
        return self.bucket.consume(1)
    
    def wait(self) -> float:
        """
        Get time to wait before next request is allowed.
        
        Returns:
            Seconds to wait
        """
        return self.bucket.wait_time()
    
    def reset(self) -> None:
        """Reset rate limiter to full capacity."""
        with self.bucket.lock:
            self.bucket.tokens = self.bucket.capacity
            self.bucket.last_refill = time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics.
        
        Returns:
            Dictionary with capacity, remaining, and reset_at
        """
        with self.bucket.lock:
            self.bucket._refill()
            
            return {
                "capacity": self.bucket.capacity,
                "remaining": int(self.bucket.tokens),
                "reset_at": datetime.fromtimestamp(
                    self.bucket.last_refill + self.bucket.capacity / self.bucket.refill_rate,
                    tz=timezone.utc
                ).isoformat()
            }


def rate_limit(
    calls: int,
    period: float,
    auto_retry: bool = False,
    handle_429: bool = False,
    max_retries: int = 3
) -> Callable:
    """
    Decorator to rate limit function calls.
    
    Uses token bucket algorithm to limit calls per period.
    Optionally handles 429 responses with exponential backoff.
    
    Args:
        calls: Maximum number of calls
        period: Time period in seconds
        auto_retry: If True, automatically wait and retry when rate limited
        handle_429: If True, catch 429 HTTPError and retry with backoff
        max_retries: Maximum retry attempts for 429 responses
    
    Example:
        @rate_limit(calls=100, period=60)
        def api_call():
            return requests.get("https://api.example.com/data")
        
        # With auto-retry
        @rate_limit(calls=10, period=1, auto_retry=True)
        def fetch_user(user_id):
            return requests.get(f"https://api.example.com/users/{user_id}")
        
        # With 429 handling
        @rate_limit(calls=100, period=60, handle_429=True, max_retries=5)
        def sync_data():
            response = requests.get("https://api.example.com/sync")
            response.raise_for_status()
            return response.json()
    """
    limiter = RateLimiter(calls=calls, period=period)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check rate limit
            if not limiter.allow():
                if auto_retry:
                    wait_time = limiter.wait()
                    time.sleep(wait_time)
                else:
                    raise RateLimitExceeded(retry_after=limiter.wait())
            
            # Handle 429 responses with exponential backoff
            if handle_429:
                retry_count = 0
                backoff = 1  # Start with 1 second
                
                while retry_count < max_retries:
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        # Check if it's a 429 response
                        is_429 = (
                            hasattr(e, 'response') and
                            hasattr(e.response, 'status_code') and
                            e.response.status_code == 429
                        )
                        
                        if is_429 and retry_count < max_retries - 1:
                            # Get Retry-After header if available
                            retry_after = None
                            if hasattr(e.response, 'headers'):
                                retry_after = e.response.headers.get('Retry-After')
                            
                            if retry_after:
                                wait_time = float(retry_after)
                            else:
                                wait_time = backoff
                                backoff *= 2  # Exponential backoff
                            
                            time.sleep(wait_time)
                            retry_count += 1
                        else:
                            raise
                
                # Final attempt
                return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    
    return decorator
