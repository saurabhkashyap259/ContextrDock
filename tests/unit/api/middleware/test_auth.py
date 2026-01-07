"""Tests for authentication middleware."""

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from src.api.middleware.auth import get_current_user, AuthenticatedUser
from src.services.auth import create_access_token, create_refresh_token


# Create test app
app = FastAPI()


@app.get("/protected")
async def protected_route(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Protected endpoint for testing."""
    return {"user_id": current_user.user_id, "email": current_user.email}


client = TestClient(app)


def test_get_current_user_valid_token() -> None:
    """Test that valid access token allows access."""
    token = create_access_token({"sub": "user@example.com", "user_id": 123})
    
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    assert response.json() == {"user_id": 123, "email": "user@example.com"}


def test_get_current_user_no_token() -> None:
    """Test that missing token returns 401."""
    response = client.get("/protected")
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_current_user_invalid_token() -> None:
    """Test that invalid token returns 401."""
    response = client.get("/protected", headers={"Authorization": "Bearer invalid.token.here"})
    
    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.json()["detail"]


def test_get_current_user_malformed_header() -> None:
    """Test that malformed Authorization header returns 401."""
    response = client.get("/protected", headers={"Authorization": "NotBearer token"})
    
    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.json()["detail"]


def test_get_current_user_refresh_token_rejected() -> None:
    """Test that refresh token is rejected for access token endpoint."""
    refresh_token = create_refresh_token({"sub": "user@example.com", "user_id": 123})
    
    response = client.get("/protected", headers={"Authorization": f"Bearer {refresh_token}"})
    
    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.json()["detail"]


def test_get_current_user_expired_token() -> None:
    """Test that expired token returns 401."""
    from datetime import datetime, timedelta
    from jose import jwt
    from src.config import settings
    
    # Create expired token
    expire = datetime.utcnow() - timedelta(hours=1)
    payload = {
        "sub": "user@example.com",
        "user_id": 123,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    expired_token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    
    response = client.get("/protected", headers={"Authorization": f"Bearer {expired_token}"})
    
    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.json()["detail"]


def test_authenticated_user_model() -> None:
    """Test AuthenticatedUser model."""
    user = AuthenticatedUser(user_id=123, email="user@example.com")
    
    assert user.user_id == 123
    assert user.email == "user@example.com"
