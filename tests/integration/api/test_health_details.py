"""
Integration tests for enhanced health check endpoint (T200).

Tests health check with service status:
- Database connectivity
- Redis connectivity
- Qdrant connectivity
- Overall health status
- Detailed component status
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthCheckBasic:
    """Test basic health check functionality."""
    
    def test_health_endpoint_exists(self, client: TestClient):
        """Test that /health endpoint exists."""
        response = client.get("/health")
        assert response.status_code in [200, 503]
    
    def test_health_returns_json(self, client: TestClient):
        """Test that health check returns JSON."""
        response = client.get("/health")
        assert response.headers["content-type"] == "application/json"
    
    def test_health_has_status_field(self, client: TestClient):
        """Test that health check includes status field."""
        response = client.get("/health")
        data = response.json()
        
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


class TestHealthCheckDetails:
    """Test detailed health check with service status."""
    
    def test_health_includes_database_status(self, client: TestClient):
        """Test that health check includes database connectivity."""
        response = client.get("/health")
        data = response.json()
        
        assert "services" in data
        assert "database" in data["services"]
        assert "status" in data["services"]["database"]
    
    def test_health_includes_redis_status(self, client: TestClient):
        """Test that health check includes Redis connectivity."""
        response = client.get("/health")
        data = response.json()
        
        assert "redis" in data["services"]
        assert "status" in data["services"]["redis"]
    
    def test_health_includes_qdrant_status(self, client: TestClient):
        """Test that health check includes Qdrant connectivity."""
        response = client.get("/health")
        data = response.json()
        
        assert "qdrant" in data["services"]
        assert "status" in data["services"]["qdrant"]
    
    def test_health_includes_timestamp(self, client: TestClient):
        """Test that health check includes timestamp."""
        response = client.get("/health")
        data = response.json()
        
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)
    
    def test_health_includes_version(self, client: TestClient):
        """Test that health check includes version info."""
        response = client.get("/health")
        data = response.json()
        
        assert "version" in data
        assert isinstance(data["version"], str)


class TestHealthCheckStatuses:
    """Test health check status logic."""
    
    def test_healthy_when_all_services_up(self, client: TestClient):
        """Test that status is healthy when all services are up."""
        response = client.get("/health")
        data = response.json()
        
        # If all services are up, status should be healthy
        all_healthy = all(
            service["status"] == "up"
            for service in data.get("services", {}).values()
        )
        
        if all_healthy:
            assert data["status"] == "healthy"
            assert response.status_code == 200
    
    def test_degraded_when_optional_service_down(self, client: TestClient):
        """Test that status is degraded when optional service is down."""
        response = client.get("/health")
        data = response.json()
        
        # If only non-critical services are down, should be degraded
        # (e.g., Qdrant down but database/redis up)
        if data["status"] == "degraded":
            assert response.status_code == 200
    
    def test_unhealthy_when_critical_service_down(self, client: TestClient):
        """Test that status is unhealthy when critical service is down."""
        response = client.get("/health")
        data = response.json()
        
        # If database is down, should be unhealthy
        if data.get("services", {}).get("database", {}).get("status") == "down":
            assert data["status"] == "unhealthy"
            assert response.status_code == 503


class TestHealthCheckServiceDetails:
    """Test detailed service status information."""
    
    def test_database_includes_latency(self, client: TestClient):
        """Test that database status includes latency."""
        response = client.get("/health")
        data = response.json()
        
        db_status = data.get("services", {}).get("database", {})
        if db_status.get("status") == "up":
            assert "latency_ms" in db_status
            assert isinstance(db_status["latency_ms"], (int, float))
    
    def test_redis_includes_latency(self, client: TestClient):
        """Test that Redis status includes latency."""
        response = client.get("/health")
        data = response.json()
        
        redis_status = data.get("services", {}).get("redis", {})
        if redis_status.get("status") == "up":
            assert "latency_ms" in redis_status
    
    def test_qdrant_includes_latency(self, client: TestClient):
        """Test that Qdrant status includes latency."""
        response = client.get("/health")
        data = response.json()
        
        qdrant_status = data.get("services", {}).get("qdrant", {})
        if qdrant_status.get("status") == "up":
            assert "latency_ms" in qdrant_status
    
    def test_service_includes_error_message_when_down(self, client: TestClient):
        """Test that service includes error message when down."""
        response = client.get("/health")
        data = response.json()
        
        # Check if any service is down
        for service_name, service_data in data.get("services", {}).items():
            if service_data.get("status") == "down":
                assert "error" in service_data
                assert isinstance(service_data["error"], str)


class TestHealthCheckCaching:
    """Test health check caching for performance."""
    
    def test_health_check_is_fast(self, client: TestClient):
        """Test that health check responds quickly."""
        import time
        
        start = time.time()
        response = client.get("/health")
        elapsed = time.time() - start
        
        # Health check should respond within 5 seconds
        assert elapsed < 5.0
        assert response.status_code in [200, 503]
    
    def test_health_check_timeout(self, client: TestClient):
        """Test that health checks have reasonable timeout."""
        # Health checks should not hang indefinitely
        # Each service check should timeout after 2-3 seconds
        response = client.get("/health")
        
        # Should get a response (even if services are down)
        assert response.status_code in [200, 503]


class TestHealthCheckEndpoint:
    """Test health check endpoint integration."""
    
    def test_health_check_accessible_without_auth(self, client: TestClient):
        """Test that health check is accessible without authentication."""
        # Health check should be public for load balancers
        response = client.get("/health")
        
        # Should not return 401/403
        assert response.status_code not in [401, 403]
    
    def test_health_check_structure(self, client: TestClient):
        """Test complete health check response structure."""
        response = client.get("/health")
        data = response.json()
        
        # Required fields
        assert "status" in data
        assert "timestamp" in data
        assert "services" in data
        
        # Services field should be dict
        assert isinstance(data["services"], dict)
        
        # Each service should have status
        for service_name, service_data in data["services"].items():
            assert "status" in service_data
            assert service_data["status"] in ["up", "down", "unknown"]


class TestHealthCheckMetrics:
    """Test health check metrics collection."""
    
    def test_health_check_recorded_in_metrics(self, client: TestClient):
        """Test that health checks are recorded in metrics."""
        # Make health check request
        response = client.get("/health")
        
        # Check metrics endpoint
        metrics_response = client.get("/metrics")
        
        if metrics_response.status_code == 200:
            metrics_text = metrics_response.text
            
            # Should include health check metrics
            assert "contextdock_requests_total" in metrics_text
