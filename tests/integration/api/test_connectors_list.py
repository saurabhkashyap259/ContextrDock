"""Integration tests for GET /v1/connectors endpoint."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.connectors import router
from src.models.connector import Connector
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app with connector routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_connectors(db_session: Session):
    """Create sample connectors for testing."""
    connectors = [
        Connector(
            workspace_id=1,
            connector_type="slack",
            display_name="Team Slack",
            config={"team_id": "T123"},
            credentials_encrypted=b"encrypted",
            is_active=True,
        ),
        Connector(
            workspace_id=1,
            connector_type="jira",
            display_name="Project Jira",
            config={"cloud_id": "abc123"},
            credentials_encrypted=b"encrypted",
            is_active=True,
        ),
        Connector(
            workspace_id=1,
            connector_type="github",
            display_name="Org GitHub",
            config={"org": "myorg"},
            credentials_encrypted=b"encrypted",
            is_active=False,
        ),
        # Different workspace
        Connector(
            workspace_id=2,
            connector_type="slack",
            display_name="Other Team",
            config={},
            credentials_encrypted=b"encrypted",
            is_active=True,
        ),
    ]
    
    for connector in connectors:
        db_session.add(connector)
    db_session.commit()
    
    # Refresh to get IDs
    for connector in connectors:
        db_session.refresh(connector)
    
    return connectors


def test_list_connectors_success(client, sample_connectors):
    """Test successful list of connectors."""
    response = client.get("/v1/connectors")
    
    assert response.status_code == 200
    data = response.json()
    
    # Should only get workspace 1 connectors
    assert data["total"] == 3
    assert len(data["connectors"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 50
    
    # Check connector types
    types = {c["connector_type"] for c in data["connectors"]}
    assert types == {"slack", "jira", "github"}


def test_list_connectors_pagination(client, sample_connectors):
    """Test pagination parameters."""
    response = client.get("/v1/connectors?page=1&page_size=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 3
    assert len(data["connectors"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_list_connectors_filter_by_type(client, sample_connectors):
    """Test filtering by connector type."""
    response = client.get("/v1/connectors?connector_type=slack")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert len(data["connectors"]) == 1
    assert data["connectors"][0]["connector_type"] == "slack"


def test_list_connectors_filter_by_active_status(client, sample_connectors):
    """Test filtering by active status."""
    # Get only active connectors
    response = client.get("/v1/connectors?is_active=true")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 2
    assert all(c["is_active"] for c in data["connectors"])
    
    # Get only inactive connectors
    response = client.get("/v1/connectors?is_active=false")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 1
    assert not data["connectors"][0]["is_active"]


def test_list_connectors_empty(client):
    """Test list with no connectors."""
    response = client.get("/v1/connectors")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0
    assert len(data["connectors"]) == 0


def test_list_connectors_response_excludes_credentials(client, sample_connectors):
    """Test that response does not include credentials."""
    response = client.get("/v1/connectors")
    
    assert response.status_code == 200
    data = response.json()
    
    for connector in data["connectors"]:
        assert "credentials" not in connector
        assert "credentials_encrypted" not in connector
