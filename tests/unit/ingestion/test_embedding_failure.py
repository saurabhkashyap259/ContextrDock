"""
Unit tests for embedding API failure handling (T195).

Tests retry logic with exponential backoff and jitter:
- Retry delays: 1s, 2s, 4s, 8s
- Random jitter to prevent thundering herd
- Transient failure recovery
- Permanent failure detection
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import random


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
        Add random jitter to base delay.
        
        Args:
            base_delay: Base delay in seconds
            
        Returns:
            Delay with jitter applied (±25%)
        """
        jitter = random.uniform(-self.jitter_range, self.jitter_range)
        return base_delay * (1 + jitter)
    
    async def call_with_retry(
        self,
        func: callable,
        *args,
        **kwargs
    ):
        """
        Call function with retry logic.
        
        Args:
            func: Async function to call
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
                result = await func(*args, **kwargs)
                return result
            
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if attempt < len(self.base_delays) - 1:
                    # Apply jitter to delay
                    delay = self.get_delay_with_jitter(base_delay)
                    
                    # Wait before retry
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    raise
        
        # Should not reach here, but raise last exception if we do
        raise last_exception


class TestEmbeddingRetryManager:
    """Test embedding API retry logic."""
    
    def test_base_delays_configured(self):
        """Test that base delays are configured correctly."""
        manager = EmbeddingRetryManager()
        assert manager.base_delays == [1, 2, 4, 8]
    
    def test_jitter_range_configured(self):
        """Test that jitter range is 25%."""
        manager = EmbeddingRetryManager()
        assert manager.jitter_range == 0.25
    
    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delays."""
        manager = EmbeddingRetryManager()
        
        base_delay = 2.0
        
        # Generate multiple jittered delays
        jittered_delays = [
            manager.get_delay_with_jitter(base_delay)
            for _ in range(100)
        ]
        
        # All should be within ±25% of base delay
        min_delay = base_delay * (1 - manager.jitter_range)
        max_delay = base_delay * (1 + manager.jitter_range)
        
        assert all(min_delay <= d <= max_delay for d in jittered_delays)
        
        # Should have variation (not all the same)
        assert len(set(jittered_delays)) > 1
    
    def test_jitter_prevents_exact_timing(self):
        """Test that jitter prevents multiple clients from retrying at exact same time."""
        manager = EmbeddingRetryManager()
        
        base_delay = 1.0
        
        # Two "clients" calculating delay
        delay1 = manager.get_delay_with_jitter(base_delay)
        delay2 = manager.get_delay_with_jitter(base_delay)
        
        # With 25% jitter, highly unlikely to be identical
        # (would happen <1% of time with floating point precision)
        assert delay1 != delay2
    
    @pytest.mark.asyncio
    async def test_successful_call_on_first_attempt(self):
        """Test successful call without retries."""
        manager = EmbeddingRetryManager()
        
        # Mock function that succeeds
        mock_func = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})
        
        result = await manager.call_with_retry(mock_func, text="test")
        
        assert result == {"embedding": [0.1, 0.2, 0.3]}
        mock_func.assert_called_once_with(text="test")
    
    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Test retry logic on transient failures."""
        manager = EmbeddingRetryManager()
        
        # Mock function that fails then succeeds
        mock_func = AsyncMock(side_effect=[
            Exception("Rate limit"),  # First attempt fails
            {"embedding": [0.1, 0.2, 0.3]},  # Second attempt succeeds
        ])
        
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await manager.call_with_retry(mock_func)
            
            # Should have slept once (with jitter applied to 1s base delay)
            assert mock_sleep.call_count == 1
            delay_arg = mock_sleep.call_args[0][0]
            
            # Delay should be around 1s with ±25% jitter
            assert 0.75 <= delay_arg <= 1.25
        
        # Function should be called twice
        assert mock_func.call_count == 2
        
        # Should eventually succeed
        assert result == {"embedding": [0.1, 0.2, 0.3]}
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Test that delays follow exponential backoff pattern."""
        manager = EmbeddingRetryManager()
        
        # Mock function that fails 3 times then succeeds
        mock_func = AsyncMock(side_effect=[
            Exception("Error 1"),
            Exception("Error 2"),
            Exception("Error 3"),
            {"embedding": [0.1, 0.2, 0.3]},
        ])
        
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await manager.call_with_retry(mock_func)
            
            # Should have slept 3 times (after first 3 failures)
            assert mock_sleep.call_count == 3
            
            # Get actual delays
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            
            # Delays should roughly follow 1s, 2s, 4s pattern (with jitter)
            assert 0.75 <= delays[0] <= 1.25  # ~1s with ±25% jitter
            assert 1.5 <= delays[1] <= 2.5   # ~2s with ±25% jitter
            assert 3.0 <= delays[2] <= 5.0   # ~4s with ±25% jitter
    
    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test failure after all retries exhausted."""
        manager = EmbeddingRetryManager()
        
        # Mock function that always fails
        mock_func = AsyncMock(side_effect=Exception("Permanent failure"))
        
        with patch('asyncio.sleep', new=AsyncMock()):
            with pytest.raises(Exception) as exc_info:
                await manager.call_with_retry(mock_func)
            
            assert "Permanent failure" in str(exc_info.value)
        
        # Should have tried 4 times (initial + 3 retries)
        assert mock_func.call_count == 4


class TestEmbeddingAPIRetry:
    """Test embedding API integration with retry logic."""
    
    @pytest.mark.asyncio
    async def test_openai_rate_limit_retry(self):
        """Test retry on OpenAI rate limit error."""
        manager = EmbeddingRetryManager()
        
        # Simulate OpenAI rate limit error
        class RateLimitError(Exception):
            pass
        
        mock_openai = AsyncMock(side_effect=[
            RateLimitError("Rate limit exceeded"),
            {"data": [{"embedding": [0.1, 0.2, 0.3]}]},
        ])
        
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await manager.call_with_retry(mock_openai)
        
        # Should retry and succeed
        assert result == {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        assert mock_openai.call_count == 2
    
    @pytest.mark.asyncio
    async def test_network_timeout_retry(self):
        """Test retry on network timeout."""
        manager = EmbeddingRetryManager()
        
        mock_api = AsyncMock(side_effect=[
            asyncio.TimeoutError("Connection timeout"),
            {"embedding": [0.1, 0.2, 0.3]},
        ])
        
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await manager.call_with_retry(mock_api)
        
        assert result == {"embedding": [0.1, 0.2, 0.3]}
    
    @pytest.mark.asyncio
    async def test_server_error_retry(self):
        """Test retry on 5xx server errors."""
        manager = EmbeddingRetryManager()
        
        class ServerError(Exception):
            pass
        
        mock_api = AsyncMock(side_effect=[
            ServerError("502 Bad Gateway"),
            {"embedding": [0.1, 0.2, 0.3]},
        ])
        
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await manager.call_with_retry(mock_api)
        
        assert result == {"embedding": [0.1, 0.2, 0.3]}


class TestJitterDistribution:
    """Test jitter distribution prevents thundering herd."""
    
    def test_jitter_spreads_retry_times(self):
        """Test that jitter spreads out retry times for multiple clients."""
        manager = EmbeddingRetryManager()
        
        base_delay = 2.0
        num_clients = 100
        
        # Simulate 100 clients calculating retry delay
        retry_times = [
            manager.get_delay_with_jitter(base_delay)
            for _ in range(num_clients)
        ]
        
        # Calculate distribution
        min_time = min(retry_times)
        max_time = max(retry_times)
        spread = max_time - min_time
        
        # Spread should be significant (close to 50% of base delay)
        expected_spread = base_delay * 0.5  # 25% + 25% = 50%
        assert spread >= expected_spread * 0.8  # Allow some variance
    
    def test_jitter_average_equals_base_delay(self):
        """Test that average jittered delay equals base delay."""
        manager = EmbeddingRetryManager()
        
        base_delay = 2.0
        num_samples = 1000
        
        # Generate many samples
        samples = [
            manager.get_delay_with_jitter(base_delay)
            for _ in range(num_samples)
        ]
        
        # Average should be close to base delay
        average = sum(samples) / len(samples)
        
        # Allow 5% variance from base delay
        assert 0.95 * base_delay <= average <= 1.05 * base_delay


class TestRetryMetrics:
    """Test retry metrics for monitoring."""
    
    @pytest.mark.asyncio
    async def test_tracks_retry_count(self):
        """Test that retry count is tracked."""
        manager = EmbeddingRetryManager()
        
        retry_count = 0
        
        async def failing_func():
            nonlocal retry_count
            retry_count += 1
            if retry_count < 3:
                raise Exception("Fail")
            return {"success": True}
        
        with patch('asyncio.sleep', new=AsyncMock()):
            result = await manager.call_with_retry(failing_func)
        
        # Should have tried 3 times
        assert retry_count == 3
        assert result == {"success": True}
    
    @pytest.mark.asyncio
    async def test_final_retry_raises_exception(self):
        """Test that final retry raises exception for error tracking."""
        manager = EmbeddingRetryManager()
        
        mock_func = AsyncMock(side_effect=Exception("Persistent error"))
        
        with patch('asyncio.sleep', new=AsyncMock()):
            with pytest.raises(Exception) as exc_info:
                await manager.call_with_retry(mock_func)
        
        # Exception should be raised for monitoring/alerting
        assert "Persistent error" in str(exc_info.value)
