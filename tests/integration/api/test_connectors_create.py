"""Integration tests for POST /v1/connectors endpoint."""

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


def test_create_connector_success(client, db_session: Session):
    """Test successful connector creation."""
    payload = {
        "connector_type": "slack",
        "display_name": "Team Slack",
        "config": {
            "team_id": "T123",
            "channels": ["general", "random"]
        },
        "credentials": {
            "access_token": "xoxb-test-token",
            "token_type": "bearer"
        },
        "sync_schedule": "0 */6 * * *",
        "is_active": True
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["connector_type"] == "slack"
    assert data["display_name"] == "Team Slack"
    assert data["config"] == payload["config"]
    assert data["is_active"] is True
    assert "credentials" not in data
    assert "id" in data
    
    # Verify in database
    connector = db_session.query(Connector).filter_by(id=data["id"]).first()
    assert connector is not None
    assert connector.connector_type == "slack"
    assert connector.credentials_encrypted is not None


def test_create_connector_with_default_schedule(client, db_session: Session):
    """Test connector creation with default sync schedule."""
    payload = {
        "connector_type": "jira",
        "display_name": "Project Jira",
        "config": {"cloud_id": "abc123"},
        "credentials": {
            "access_token": "test-token"
        }
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Should have default schedule
    assert data["sync_schedule"] is None or data["sync_schedule"] == "0 */6 * * *"


def test_create_connector_invalid_type(client):
    """Test creation with invalid connector type."""
    payload = {
        "connector_type": "invalid_type",
        "display_name": "Invalid",
        "config": {},
        "credentials": {
            "access_token": "test-token"
        }
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 422  # Validation error
    data = response.json()
    assert "detail" in data


def test_create_connector_invalid_cron_schedule(client):
    """Test creation with invalid cron expression."""
    payload = {
        "connector_type": "slack",
        "display_name": "Team Slack",
        "config": {},
        "credentials": {
            "access_token": "test-token"
        },
        "sync_schedule": "invalid cron"
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 422  # Validation error
    data = response.json()
    assert "detail" in data


def test_create_connector_missing_credentials(client):
    """Test creation without credentials."""
    payload = {
        "connector_type": "slack",
        "display_name": "Team Slack",
        "config": {}
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 422  # Validation error


def test_create_connector_empty_display_name(client):
    """Test creation with empty display name."""
    payload = {
        "connector_type": "slack",
        "display_name": "",
        "config": {},
        "credentials": {
            "access_token": "test-token"
        }
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 422  # Validation error


def test_create_connector_credentials_encrypted(client, db_session: Session):
    """Test that credentials are encrypted in database."""
    payload = {
        "connector_type": "github",
        "display_name": "Org GitHub",
        "config": {"org": "myorg"},
        "credentials": {
            "access_token": "ghp_secret_token",
            "refresh_token": "refresh_secret"
        }
    }
    
    response = client.post("/v1/connectors", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Get from database
    connector = db_session.query(Connector).filter_by(id=data["id"]).first()
    
    # Credentials should be encrypted (not plain text)
    encrypted = connector.credentials_encrypted
    assert encrypted is not None
    assert b"ghp_secret_token" not in encrypted  # Should not contain plain text


def test_create_connector_multiple_types(client, db_session: Session):
    """Test creating multiple connectors of different types."""
    types = ["slack", "jira", "confluence", "github", "figma", "dropbox"]
    
    for connector_type in types:
        payload = {
            "connector_type": connector_type,
            "display_name": f"Test {connector_type}",
            "config": {},
            "credentials": {
                "access_token": f"token-{connector_type}"
            }
        }
        
        response = client.post("/v1/connectors", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert data["connector_type"] == connector_type
    
    # Verify all created
    count = db_session.query(Connector).count()
    assert count == len(types)
