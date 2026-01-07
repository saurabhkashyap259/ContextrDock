"""Tests for OAuth2 helper."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import requests

from src.connectors.sdk.oauth import OAuth2Helper, OAuth2Config, OAuth2Token


def test_oauth2_config_creation():
    """Test OAuth2Config dataclass creation."""
    config = OAuth2Config(
        client_id="test_client_id",
        client_secret="test_client_secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="https://app.example.com/callback",
        scopes=["read:data", "write:data"]
    )
    
    assert config.client_id == "test_client_id"
    assert config.client_secret == "test_client_secret"
    assert config.authorization_url == "https://example.com/oauth/authorize"
    assert config.token_url == "https://example.com/oauth/token"
    assert config.redirect_uri == "https://app.example.com/callback"
    assert config.scopes == ["read:data", "write:data"]


def test_oauth2_token_creation():
    """Test OAuth2Token dataclass creation."""
    token = OAuth2Token(
        access_token="access_abc123",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="refresh_xyz789",
        scope="read:data write:data"
    )
    
    assert token.access_token == "access_abc123"
    assert token.token_type == "Bearer"
    assert token.expires_in == 3600
    assert token.refresh_token == "refresh_xyz789"
    assert token.scope == "read:data write:data"


def test_oauth2_token_is_expired():
    """Test token expiration checking."""
    # Create token that expires in 1 hour
    token = OAuth2Token(
        access_token="test_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="refresh_token"
    )
    
    # Should not be expired (with 5 minute buffer)
    assert not token.is_expired()
    
    # Manually set expires_at to past time
    token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert token.is_expired()


def test_oauth2_token_expires_soon():
    """Test checking if token expires within buffer period."""
    # Create token that expires in 3 minutes
    token = OAuth2Token(
        access_token="test_token",
        token_type="Bearer",
        expires_in=180,  # 3 minutes
        refresh_token="refresh_token"
    )
    
    # Should expire soon (default buffer is 5 minutes)
    assert token.expires_soon()
    
    # Create token that expires in 20 minutes
    token2 = OAuth2Token(
        access_token="test_token",
        token_type="Bearer",
        expires_in=1200,  # 20 minutes
        refresh_token="refresh_token"
    )
    
    # Should not expire soon
    assert not token2.expires_soon()


def test_oauth2_helper_initialization():
    """Test OAuth2Helper initialization."""
    config = OAuth2Config(
        client_id="test_id",
        client_secret="test_secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="https://app.example.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    assert helper.config == config
    assert helper.token is None


def test_get_authorization_url():
    """Test generating authorization URL."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read:user", "read:repo"]
    )
    
    helper = OAuth2Helper(config)
    auth_url, state = helper.get_authorization_url()
    
    assert "https://provider.com/authorize" in auth_url
    assert "client_id=test_client" in auth_url
    assert "redirect_uri=https%3A%2F%2Fapp.com%2Fcallback" in auth_url
    assert "scope=read%3Auser+read%3Arepo" in auth_url
    assert "state=" in auth_url
    assert state is not None
    assert len(state) > 10  # State should be random string


def test_get_authorization_url_with_pkce():
    """Test generating authorization URL with PKCE."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    auth_url, state = helper.get_authorization_url(use_pkce=True)
    
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert helper._code_verifier is not None  # PKCE verifier stored


@patch('requests.post')
def test_exchange_code_for_token(mock_post):
    """Test exchanging authorization code for access token."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "new_refresh_token",
        "scope": "read write"
    }
    mock_post.return_value = mock_response
    
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read", "write"]
    )
    
    helper = OAuth2Helper(config)
    token = helper.exchange_code_for_token(code="auth_code_123")
    
    assert token.access_token == "new_access_token"
    assert token.token_type == "Bearer"
    assert token.expires_in == 3600
    assert token.refresh_token == "new_refresh_token"
    assert helper.token == token  # Token stored in helper
    
    # Verify API call
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://provider.com/token"
    assert call_args[1]["data"]["code"] == "auth_code_123"
    assert call_args[1]["data"]["grant_type"] == "authorization_code"


@patch('requests.post')
def test_exchange_code_for_token_with_pkce(mock_post):
    """Test exchanging code with PKCE verifier."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "refresh_token"
    }
    mock_post.return_value = mock_response
    
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    helper._code_verifier = "test_verifier_12345"
    
    token = helper.exchange_code_for_token(code="auth_code")
    
    # Verify PKCE verifier sent
    call_args = mock_post.call_args
    assert call_args[1]["data"]["code_verifier"] == "test_verifier_12345"


@patch('requests.post')
def test_exchange_code_for_token_error(mock_post):
    """Test handling error when exchanging code."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "Invalid authorization code"
    }
    mock_post.return_value = mock_response
    
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    with pytest.raises(Exception, match="OAuth2 token exchange failed"):
        helper.exchange_code_for_token(code="invalid_code")


@patch('requests.post')
def test_refresh_token(mock_post):
    """Test refreshing an access token."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "refreshed_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "new_refresh_token"
    }
    mock_post.return_value = mock_response
    
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    # Set existing token
    old_token = OAuth2Token(
        access_token="old_access",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="old_refresh"
    )
    helper.token = old_token
    
    new_token = helper.refresh_token()
    
    assert new_token.access_token == "refreshed_access_token"
    assert new_token.refresh_token == "new_refresh_token"
    assert helper.token == new_token  # Token updated
    
    # Verify API call
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[1]["data"]["grant_type"] == "refresh_token"
    assert call_args[1]["data"]["refresh_token"] == "old_refresh"


@patch('requests.post')
def test_refresh_token_no_existing_token(mock_post):
    """Test refreshing when no token exists."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    with pytest.raises(Exception, match="No token to refresh"):
        helper.refresh_token()


@patch('requests.post')
def test_get_valid_token_with_fresh_token(mock_post):
    """Test get_valid_token with fresh token (no refresh needed)."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    # Set fresh token (expires in 1 hour)
    fresh_token = OAuth2Token(
        access_token="fresh_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="refresh"
    )
    helper.token = fresh_token
    
    token = helper.get_valid_token()
    
    assert token == fresh_token
    mock_post.assert_not_called()  # No refresh needed


@patch('requests.post')
def test_get_valid_token_with_expired_token(mock_post):
    """Test get_valid_token with expired token (refresh needed)."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "refreshed_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "new_refresh"
    }
    mock_post.return_value = mock_response
    
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    # Set expired token
    expired_token = OAuth2Token(
        access_token="expired_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="refresh"
    )
    expired_token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    helper.token = expired_token
    
    token = helper.get_valid_token()
    
    assert token.access_token == "refreshed_token"
    mock_post.assert_called_once()  # Refresh called


def test_get_valid_token_no_token():
    """Test get_valid_token when no token exists."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    with pytest.raises(Exception, match="No token available"):
        helper.get_valid_token()


def test_revoke_token():
    """Test revoking a token."""
    config = OAuth2Config(
        client_id="test_client",
        client_secret="test_secret",
        authorization_url="https://provider.com/authorize",
        token_url="https://provider.com/token",
        redirect_uri="https://app.com/callback",
        scopes=["read"]
    )
    
    helper = OAuth2Helper(config)
    
    # Set token
    token = OAuth2Token(
        access_token="access_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="refresh_token"
    )
    helper.token = token
    
    # Revoke
    helper.revoke_token()
    
    assert helper.token is None
