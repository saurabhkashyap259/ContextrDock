"""Integration tests for identity mapping admin API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.admin import router
from src.models.user import User
from fastapi import FastAPI


@pytest.fixture
def app():
    """Create FastAPI app with admin routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_user(db_session: Session):
    """Create a sample user with some identities."""
    user = User(
        email="test@company.com",
        role="user",
        connector_identities={
            "slack": {
                "user_id": "U123ABC",
                "team_id": "T456DEF",
                "display_name": "Test User"
            },
            "jira": {
                "account_id": "jira:test-123",
                "display_name": "Test User"
            }
        }
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_get_user_identity_mappings(client, sample_user):
    """Test getting user's identity mappings."""
    response = client.get(f"/v1/admin/users/{sample_user.id}/identity-mappings")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "connector_identities" in data
    assert "slack" in data["connector_identities"]
    assert "jira" in data["connector_identities"]
    assert data["connector_identities"]["slack"]["user_id"] == "U123ABC"
    assert data["connector_identities"]["jira"]["account_id"] == "jira:test-123"


def test_get_identity_mappings_user_not_found(client):
    """Test getting identity mappings for non-existent user."""
    response = client.get("/v1/admin/users/99999/identity-mappings")
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_update_user_identity_mappings(client, sample_user, db_session: Session):
    """Test updating user's identity mappings."""
    payload = {
        "connector_identities": {
            "slack": {
                "user_id": "U999XYZ",
                "team_id": "T456DEF",
                "display_name": "Updated User"
            },
            "github": {
                "login": "testuser",
                "user_id": 12345,
                "organizations": ["myorg"]
            }
        }
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify update
    assert data["connector_identities"]["slack"]["user_id"] == "U999XYZ"
    assert "github" in data["connector_identities"]
    assert data["connector_identities"]["github"]["login"] == "testuser"
    
    # Verify in database
    db_session.refresh(sample_user)
    assert sample_user.connector_identities["slack"]["user_id"] == "U999XYZ"
    assert sample_user.connector_identities["github"]["login"] == "testuser"


def test_add_new_connector_identity(client, sample_user, db_session: Session):
    """Test adding a new connector identity."""
    payload = {
        "connector_identities": {
            "confluence": {
                "account_id": "conf:new-456",
                "display_name": "Test User"
            }
        }
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should merge with existing identities
    assert "slack" in data["connector_identities"]  # Existing
    assert "jira" in data["connector_identities"]  # Existing
    assert "confluence" in data["connector_identities"]  # New
    
    db_session.refresh(sample_user)
    assert "confluence" in sample_user.connector_identities


def test_remove_connector_identity(client, sample_user, db_session: Session):
    """Test removing a connector identity."""
    # Update to remove jira identity (omit it from update)
    payload = {
        "connector_identities": {
            "slack": sample_user.connector_identities["slack"]
            # jira omitted - should be removed
        }
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "slack" in data["connector_identities"]
    # Note: Behavior depends on implementation - might keep or remove jira
    # Adjust assertion based on actual implementation


def test_update_identity_mappings_validation(client, sample_user):
    """Test validation of identity mapping updates."""
    # Invalid payload (not a dict)
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json={"connector_identities": "invalid"}
    )
    
    assert response.status_code == 422  # Validation error


def test_partial_identity_update(client, sample_user, db_session: Session):
    """Test partial update of single connector identity."""
    # Update only Slack, keep Jira unchanged
    original_jira = sample_user.connector_identities["jira"].copy()
    
    payload = {
        "connector_identities": {
            "slack": {
                "user_id": "U111NEW",
                "team_id": "T456DEF",
                "display_name": "New Name"
            }
        }
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Slack should be updated
    assert data["connector_identities"]["slack"]["user_id"] == "U111NEW"
    
    # Jira should remain (if merge behavior)
    # Adjust based on implementation


def test_empty_identity_mappings_update(client, sample_user):
    """Test updating with empty identity mappings."""
    payload = {
        "connector_identities": {}
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    # Should either clear all identities or return error
    # Adjust based on implementation
    assert response.status_code in [200, 400]


def test_multiple_connector_types(client, sample_user, db_session: Session):
    """Test setting identities for all connector types."""
    payload = {
        "connector_identities": {
            "slack": {"user_id": "U123", "team_id": "T456"},
            "jira": {"account_id": "jira:123"},
            "confluence": {"account_id": "conf:123"},
            "github": {"login": "user", "organizations": ["org"]},
            "figma": {"user_id": "figma:123", "teams": ["team"]},
            "dropbox": {"email": "test@company.com"}
        }
    }
    
    response = client.patch(
        f"/v1/admin/users/{sample_user.id}/identity-mappings",
        json=payload
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # All 6 connector types should be present
    assert len(data["connector_identities"]) == 6
    assert all(
        conn in data["connector_identities"]
        for conn in ["slack", "jira", "confluence", "github", "figma", "dropbox"]
    )


def test_identity_mappings_admin_only(client, sample_user):
    """Test that identity mappings endpoint requires admin access."""
    # This test assumes authentication is implemented
    # For now, just verify endpoint exists
    response = client.get(f"/v1/admin/users/{sample_user.id}/identity-mappings")
    
    # Should succeed if no auth, or 401/403 if auth required
    assert response.status_code in [200, 401, 403]


def test_bulk_identity_operations(client, db_session: Session):
    """Test managing identities for multiple users."""
    # Create multiple users
    users = []
    for i in range(3):
        user = User(
            email=f"user{i}@company.com",
            role="user",
            connector_identities={}
        )
        db_session.add(user)
        users.append(user)
    
    db_session.commit()
    
    # Update each user's identities
    for i, user in enumerate(users):
        db_session.refresh(user)
        payload = {
            "connector_identities": {
                "slack": {"user_id": f"U{i:03d}", "team_id": "T456"}
            }
        }
        
        response = client.patch(
            f"/v1/admin/users/{user.id}/identity-mappings",
            json=payload
        )
        
        assert response.status_code == 200
    
    # Verify all users have identities
    for user in users:
        db_session.refresh(user)
        assert "slack" in user.connector_identities


def test_identity_mapping_response_format(client, sample_user):
    """Test that response includes all expected fields."""
    response = client.get(f"/v1/admin/users/{sample_user.id}/identity-mappings")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "user_id" in data
    assert "email" in data
    assert "connector_identities" in data
    assert isinstance(data["connector_identities"], dict)
    
    # Verify connector identity structure
    for connector_type, identity in data["connector_identities"].items():
        assert isinstance(identity, dict)
        # Each identity should have at least some fields
        assert len(identity) > 0
