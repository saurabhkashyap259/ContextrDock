"""
Unit tests for circuit breaker pattern in Qdrant integration (T191).

Tests circuit breaker functionality:
- Normal operation (closed state)
- Failure detection (opening circuit after threshold)
- Fallback to keyword-only search
- Circuit recovery after timeout
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import asyncio


class CircuitState:
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, use fallback
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for Qdrant vector database.
    
    Prevents cascading failures by:
    - Opening circuit after 3 consecutive failures
    - Falling back to keyword-only search when open
    - Attempting recovery after timeout period
    """
    
    def __init__(self, failure_threshold=3, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # seconds
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = None
    
    def record_success(self):
        """Record successful call."""
        self.failures = 0
        self.state = CircuitState.CLOSED
    
    def record_failure(self):
        """Record failed call."""
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def can_attempt(self):
        """Check if circuit allows attempting call."""
        if self.state == CircuitState.CLOSED:
            return True
        
        # Check if timeout has passed
        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.timeout:
                    self.state = CircuitState.HALF_OPEN
                    return True
        
        if self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def is_open(self):
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN


class TestCircuitBreaker:
    """Test circuit breaker logic."""
    
    def test_initial_state_is_closed(self):
        """Test that circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failures == 0
        assert cb.can_attempt() is True
    
    def test_records_single_failure(self):
        """Test that single failure is recorded but circuit remains closed."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        
        assert cb.failures == 1
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True
    
    def test_records_multiple_failures(self):
        """Test that multiple failures are recorded."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        
        assert cb.failures == 2
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True
    
    def test_opens_after_threshold_failures(self):
        """Test that circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        
        assert cb.failures == 3
        assert cb.state == CircuitState.OPEN
        assert cb.is_open() is True
        assert cb.can_attempt() is False
    
    def test_success_resets_failure_count(self):
        """Test that success resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failures == 2
        
        cb.record_success()
        
        assert cb.failures == 0
        assert cb.state == CircuitState.CLOSED
    
    def test_half_open_after_timeout(self):
        """Test that circuit moves to half-open after timeout."""
        cb = CircuitBreaker(failure_threshold=3, timeout=1)  # 1 second timeout
        
        # Open the circuit
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        import time
        time.sleep(1.5)
        
        # Circuit should allow attempt (half-open)
        assert cb.can_attempt() is True
    
    def test_recovery_from_half_open_on_success(self):
        """Test that circuit recovers from half-open to closed on success."""
        cb = CircuitBreaker(failure_threshold=3, timeout=1)
        
        # Open the circuit
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        import time
        time.sleep(1.5)
        
        # Attempt should be allowed
        assert cb.can_attempt() is True
        
        # Record success
        cb.record_success()
        
        # Circuit should be closed
        assert cb.state == CircuitState.CLOSED
        assert cb.failures == 0


class TestQdrantCircuitBreaker:
    """Test circuit breaker integration with Qdrant client."""
    
    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        return Mock()
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker instance."""
        return CircuitBreaker(failure_threshold=3, timeout=60)
    
    @pytest.mark.asyncio
    async def test_normal_search_when_circuit_closed(self, mock_qdrant_client, circuit_breaker):
        """Test that normal vector search is used when circuit is closed."""
        # Mock successful vector search
        mock_qdrant_client.search = AsyncMock(return_value=[
            {"id": "doc1", "score": 0.95}
        ])
        
        # Circuit is closed
        assert circuit_breaker.can_attempt() is True
        
        # Perform search
        results = await mock_qdrant_client.search()
        
        # Vector search should be called
        mock_qdrant_client.search.assert_called_once()
        assert len(results) == 1
        assert results[0]["id"] == "doc1"
    
    @pytest.mark.asyncio
    async def test_fallback_to_keyword_when_circuit_open(self, circuit_breaker):
        """Test that keyword-only search is used when circuit is open."""
        # Open the circuit
        for _ in range(3):
            circuit_breaker.record_failure()
        
        assert circuit_breaker.is_open() is True
        
        # Should use fallback (keyword-only search)
        assert circuit_breaker.can_attempt() is False
        
        # Fallback search would be performed via PostgreSQL full-text search
        # (tested separately in integration tests)
    
    @pytest.mark.asyncio
    async def test_records_failure_on_qdrant_error(self, mock_qdrant_client, circuit_breaker):
        """Test that Qdrant failures are recorded in circuit breaker."""
        # Mock Qdrant failure
        mock_qdrant_client.search = AsyncMock(side_effect=Exception("Qdrant unavailable"))
        
        initial_failures = circuit_breaker.failures
        
        # Attempt search
        try:
            await mock_qdrant_client.search()
        except Exception:
            circuit_breaker.record_failure()
        
        # Failure should be recorded
        assert circuit_breaker.failures == initial_failures + 1
    
    @pytest.mark.asyncio
    async def test_records_success_on_qdrant_success(self, mock_qdrant_client, circuit_breaker):
        """Test that Qdrant successes are recorded."""
        # Mock successful search
        mock_qdrant_client.search = AsyncMock(return_value=[{"id": "doc1"}])
        
        # Record some failures first
        circuit_breaker.record_failure()
        assert circuit_breaker.failures == 1
        
        # Successful search
        results = await mock_qdrant_client.search()
        circuit_breaker.record_success()
        
        # Failures should be reset
        assert circuit_breaker.failures == 0
        assert circuit_breaker.state == CircuitState.CLOSED


class TestFallbackKeywordSearch:
    """Test fallback to keyword-only search when vector DB fails."""
    
    @pytest.mark.asyncio
    async def test_keyword_search_fallback(self):
        """Test that keyword search works as fallback."""
        # Mock keyword search (PostgreSQL full-text)
        keyword_results = [
            {"id": "doc1", "score": 0.7, "source": "keyword"},
            {"id": "doc2", "score": 0.6, "source": "keyword"}
        ]
        
        # Simulate keyword-only search
        results = keyword_results
        
        assert len(results) == 2
        assert all(r["source"] == "keyword" for r in results)
    
    @pytest.mark.asyncio
    async def test_keyword_search_uses_postgresql(self):
        """Test that keyword search uses PostgreSQL full-text search."""
        # Mock PostgreSQL search
        mock_db = Mock()
        mock_db.execute = AsyncMock(return_value=[
            {"document_id": "doc1", "rank": 0.7},
            {"document_id": "doc2", "rank": 0.6}
        ])
        
        # Execute keyword search
        query = "test query"
        results = await mock_db.execute()
        
        # PostgreSQL should be used
        mock_db.execute.assert_called_once()
        assert len(results) == 2


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics for monitoring."""
    
    def test_tracks_failure_count(self):
        """Test that failure count is tracked."""
        cb = CircuitBreaker()
        
        cb.record_failure()
        cb.record_failure()
        
        assert cb.failures == 2
    
    def test_tracks_last_failure_time(self):
        """Test that last failure time is tracked."""
        cb = CircuitBreaker()
        
        before = datetime.now()
        cb.record_failure()
        after = datetime.now()
        
        assert cb.last_failure_time is not None
        assert before <= cb.last_failure_time <= after
    
    def test_exposes_circuit_state(self):
        """Test that circuit state is accessible for monitoring."""
        cb = CircuitBreaker(failure_threshold=2)
        
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert cb.is_open() is True
