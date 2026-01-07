"""Integration tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


def test_health_endpoint_returns_200() -> None:
    """Test that /health endpoint returns 200 OK."""
    response = client.get("/health")
    
    assert response.status_code == 200


def test_health_endpoint_response_format() -> None:
    """Test that /health endpoint returns expected JSON structure."""
    response = client.get("/health")
    data = response.json()
    
    assert "status" in data
    assert "service" in data
    assert "version" in data
    assert "environment" in data
    
    assert data["status"] == "healthy"
    assert data["service"] == "contextdock-api"
    assert data["version"] == "0.1.0"


def test_root_endpoint() -> None:
    """Test that root endpoint returns 200 OK."""
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "message" in data
    assert data["message"] == "ContextDock API"


def test_health_endpoint_always_accessible() -> None:
    """Test that /health endpoint is accessible without authentication."""
    # Health check should not require authentication
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_openapi_docs_available_in_development() -> None:
    """Test that OpenAPI docs are available (in development mode)."""
    from src.config import settings
    
    if settings.is_development:
        response = client.get("/docs")
        assert response.status_code == 200
        
        response = client.get("/openapi.json")
        assert response.status_code == 200
