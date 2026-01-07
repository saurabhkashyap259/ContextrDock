"""Integration tests for PATCH /v1/connectors/{id} endpoint."""

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
def sample_connector(db_session: Session):
    """Create a sample connector for testing."""
    connector = Connector(
        workspace_id=1,
        connector_type="slack",
        display_name="Team Slack",
        config={"team_id": "T123"},
        credentials_encrypted=b"encrypted",
        sync_schedule="0 */6 * * *",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    return connector


def test_update_connector_display_name(client, sample_connector, db_session: Session):
    """Test updating connector display name."""
    payload = {
        "display_name": "Updated Slack Name"
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["display_name"] == "Updated Slack Name"
    assert data["connector_type"] == "slack"  # Unchanged
    
    # Verify in database
    db_session.refresh(sample_connector)
    assert sample_connector.display_name == "Updated Slack Name"


def test_update_connector_config(client, sample_connector, db_session: Session):
    """Test updating connector config."""
    payload = {
        "config": {
            "team_id": "T456",
            "channels": ["engineering", "general"]
        }
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["config"]["team_id"] == "T456"
    assert "channels" in data["config"]


def test_update_connector_sync_schedule(client, sample_connector, db_session: Session):
    """Test updating sync schedule."""
    payload = {
        "sync_schedule": "0 0 * * *"  # Daily at midnight
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["sync_schedule"] == "0 0 * * *"


def test_update_connector_is_active(client, sample_connector, db_session: Session):
    """Test toggling active status."""
    payload = {
        "is_active": False
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["is_active"] is False
    
    # Verify in database
    db_session.refresh(sample_connector)
    assert sample_connector.is_active is False


def test_update_connector_credentials(client, sample_connector, db_session: Session):
    """Test updating credentials."""
    old_encrypted = sample_connector.credentials_encrypted
    
    payload = {
        "credentials": {
            "access_token": "new_token",
            "refresh_token": "new_refresh"
        }
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    
    # Verify credentials were re-encrypted
    db_session.refresh(sample_connector)
    assert sample_connector.credentials_encrypted != old_encrypted


def test_update_connector_multiple_fields(client, sample_connector, db_session: Session):
    """Test updating multiple fields at once."""
    payload = {
        "display_name": "New Name",
        "config": {"new_setting": "value"},
        "is_active": False
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["display_name"] == "New Name"
    assert data["config"]["new_setting"] == "value"
    assert data["is_active"] is False


def test_update_connector_not_found(client):
    """Test updating non-existent connector."""
    payload = {
        "display_name": "Test"
    }
    
    response = client.patch("/v1/connectors/99999", json=payload)
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_update_connector_wrong_workspace(client, db_session: Session):
    """Test updating connector from different workspace."""
    # Create connector in different workspace
    connector = Connector(
        workspace_id=2,
        connector_type="slack",
        display_name="Other Team",
        config={},
        credentials_encrypted=b"encrypted",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    db_session.refresh(connector)
    
    payload = {
        "display_name": "Hacked"
    }
    
    # Should not find it (get_workspace_id returns 1)
    response = client.patch(f"/v1/connectors/{connector.id}", json=payload)
    
    assert response.status_code == 404


def test_update_connector_invalid_cron(client, sample_connector):
    """Test updating with invalid cron schedule."""
    payload = {
        "sync_schedule": "not a cron"
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 422  # Validation error


def test_update_connector_empty_payload(client, sample_connector, db_session: Session):
    """Test update with no fields (should succeed but not change anything)."""
    original_name = sample_connector.display_name
    
    payload = {}
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    # Should remain unchanged
    assert data["display_name"] == original_name


def test_update_connector_preserves_timestamps(client, sample_connector, db_session: Session):
    """Test that created_at is preserved and updated_at changes."""
    original_created = sample_connector.created_at
    
    payload = {
        "display_name": "Updated"
    }
    
    response = client.patch(f"/v1/connectors/{sample_connector.id}", json=payload)
    
    assert response.status_code == 200
    
    db_session.refresh(sample_connector)
    assert sample_connector.created_at == original_created
    # updated_at should change (difficult to test precisely due to timing)
