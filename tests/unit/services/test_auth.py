"""Tests for JWT authentication service."""

import pytest
from datetime import datetime, timedelta
from jose import jwt, JWTError

from src.services.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    decode_token,
    TokenData,
)
from src.config import settings


def test_create_access_token() -> None:
    """Test creating an access token."""
    data = {"sub": "user@example.com", "user_id": 123}
    token = create_access_token(data)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode and verify
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["sub"] == "user@example.com"
    assert decoded["user_id"] == 123
    assert decoded["type"] == "access"
    assert "exp" in decoded
    assert "iat" in decoded


def test_create_refresh_token() -> None:
    """Test creating a refresh token."""
    data = {"sub": "user@example.com", "user_id": 123}
    token = create_refresh_token(data)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode and verify
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["sub"] == "user@example.com"
    assert decoded["user_id"] == 123
    assert decoded["type"] == "refresh"
    assert "exp" in decoded
    assert "iat" in decoded


def test_access_token_expiration() -> None:
    """Test that access token has correct expiration (15 minutes)."""
    data = {"sub": "user@example.com"}
    token = create_access_token(data)
    
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    exp_timestamp = decoded["exp"]
    iat_timestamp = decoded["iat"]
    
    # Check expiration is approximately 15 minutes from issued time
    expiration_delta = exp_timestamp - iat_timestamp
    assert 14 * 60 < expiration_delta < 16 * 60  # 14-16 minutes tolerance


def test_refresh_token_expiration() -> None:
    """Test that refresh token has correct expiration (7 days)."""
    data = {"sub": "user@example.com"}
    token = create_refresh_token(data)
    
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    exp_timestamp = decoded["exp"]
    iat_timestamp = decoded["iat"]
    
    # Check expiration is approximately 7 days from issued time
    expiration_delta = exp_timestamp - iat_timestamp
    expected_seconds = 7 * 24 * 60 * 60
    assert expected_seconds - 60 < expiration_delta < expected_seconds + 60  # 1 minute tolerance


def test_verify_token_valid() -> None:
    """Test verifying a valid token."""
    data = {"sub": "user@example.com", "user_id": 123}
    token = create_access_token(data)
    
    token_data = verify_token(token)
    
    assert token_data is not None
    assert token_data.email == "user@example.com"
    assert token_data.user_id == 123
    assert token_data.token_type == "access"


def test_verify_token_invalid() -> None:
    """Test verifying an invalid token returns None."""
    invalid_token = "invalid.token.here"
    token_data = verify_token(invalid_token)
    
    assert token_data is None


def test_verify_token_expired() -> None:
    """Test verifying an expired token returns None."""
    data = {"sub": "user@example.com"}
    # Create token that expired 1 hour ago
    expire = datetime.utcnow() - timedelta(hours=1)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    expired_token = jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)
    
    token_data = verify_token(expired_token)
    
    assert token_data is None


def test_verify_token_wrong_type() -> None:
    """Test that refresh token is rejected when access token expected."""
    data = {"sub": "user@example.com", "user_id": 123}
    refresh_token = create_refresh_token(data)
    
    # Try to verify refresh token as access token
    token_data = verify_token(refresh_token, expected_type="access")
    
    assert token_data is None


def test_decode_token() -> None:
    """Test decoding token without validation."""
    data = {"sub": "user@example.com", "user_id": 123, "custom_field": "value"}
    token = create_access_token(data)
    
    payload = decode_token(token)
    
    assert payload is not None
    assert payload["sub"] == "user@example.com"
    assert payload["user_id"] == 123
    assert payload["custom_field"] == "value"
    assert payload["type"] == "access"


def test_token_data_model() -> None:
    """Test TokenData model."""
    token_data = TokenData(
        email="user@example.com",
        user_id=123,
        token_type="access"
    )
    
    assert token_data.email == "user@example.com"
    assert token_data.user_id == 123
    assert token_data.token_type == "access"
