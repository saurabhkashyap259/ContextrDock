"""OAuth2 helper for connector authentication."""

import secrets
import hashlib
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import requests


@dataclass
class OAuth2Config:
    """OAuth2 configuration for a connector."""
    
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    redirect_uri: str
    scopes: list[str]
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.client_id:
            raise ValueError("client_id is required")
        if not self.token_url:
            raise ValueError("token_url is required")


@dataclass
class OAuth2Token:
    """OAuth2 access token with metadata."""
    
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    expires_at: datetime = field(init=False)
    
    def __post_init__(self):
        """Calculate expiration time."""
        self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)
    
    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired.
        
        Args:
            buffer_seconds: Time buffer before expiration (default 5 minutes)
        
        Returns:
            True if token is expired or will expire within buffer period
        """
        return datetime.now(timezone.utc) >= self.expires_at - timedelta(seconds=buffer_seconds)
    
    def expires_soon(self, buffer_seconds: int = 300) -> bool:
        """
        Check if token will expire soon.
        
        Args:
            buffer_seconds: Time threshold for "soon" (default 5 minutes)
        
        Returns:
            True if token will expire within buffer period
        """
        return self.is_expired(buffer_seconds)


class OAuth2Helper:
    """
    OAuth2 helper for authorization code flow with PKCE support.
    
    Handles:
    - Authorization URL generation with state parameter
    - Code exchange for access token
    - Token refresh with automatic expiration handling
    - PKCE (Proof Key for Code Exchange) for enhanced security
    
    Example:
        config = OAuth2Config(
            client_id="app_id",
            client_secret="app_secret",
            authorization_url="https://provider.com/oauth/authorize",
            token_url="https://provider.com/oauth/token",
            redirect_uri="https://app.com/callback",
            scopes=["read:data"]
        )
        
        helper = OAuth2Helper(config)
        
        # Step 1: Get authorization URL
        auth_url, state = helper.get_authorization_url(use_pkce=True)
        # Redirect user to auth_url
        
        # Step 2: After callback, exchange code for token
        token = helper.exchange_code_for_token(code="received_code")
        
        # Step 3: Use token (auto-refresh if expired)
        valid_token = helper.get_valid_token()
        headers = {"Authorization": f"Bearer {valid_token.access_token}"}
    """
    
    def __init__(self, config: OAuth2Config):
        """
        Initialize OAuth2 helper.
        
        Args:
            config: OAuth2 configuration
        """
        self.config = config
        self.token: Optional[OAuth2Token] = None
        self._code_verifier: Optional[str] = None
    
    def get_authorization_url(self, use_pkce: bool = False, state: Optional[str] = None) -> tuple[str, str]:
        """
        Generate authorization URL for user consent.
        
        Args:
            use_pkce: Whether to use PKCE (recommended for SPAs and mobile apps)
            state: Custom state parameter (auto-generated if not provided)
        
        Returns:
            Tuple of (authorization_url, state)
        """
        if state is None:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "response_type": "code"
        }
        
        # Add PKCE parameters
        if use_pkce:
            self._code_verifier = secrets.token_urlsafe(64)
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(self._code_verifier.encode()).digest()
            ).decode().rstrip("=")
            
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        
        auth_url = f"{self.config.authorization_url}?{urlencode(params)}"
        return auth_url, state
    
    def exchange_code_for_token(self, code: str) -> OAuth2Token:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
        
        Returns:
            OAuth2Token with access and refresh tokens
        
        Raises:
            Exception: If token exchange fails
        """
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        # Add PKCE verifier if used
        if self._code_verifier:
            data["code_verifier"] = self._code_verifier
        
        response = requests.post(
            self.config.token_url,
            data=data,
            headers={"Accept": "application/json"}
        )
        
        if response.status_code != 200:
            error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
            error_msg = error_data.get("error_description", f"Status {response.status_code}")
            raise Exception(f"OAuth2 token exchange failed: {error_msg}")
        
        token_data = response.json()
        token = OAuth2Token(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope")
        )
        
        self.token = token
        self._code_verifier = None  # Clear verifier after use
        
        return token
    
    def refresh_token(self) -> OAuth2Token:
        """
        Refresh access token using refresh token.
        
        Returns:
            New OAuth2Token with refreshed access token
        
        Raises:
            Exception: If no token to refresh or refresh fails
        """
        if not self.token or not self.token.refresh_token:
            raise Exception("No token to refresh")
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.token.refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret
        }
        
        response = requests.post(
            self.config.token_url,
            data=data,
            headers={"Accept": "application/json"}
        )
        
        if response.status_code != 200:
            error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
            error_msg = error_data.get("error_description", f"Status {response.status_code}")
            raise Exception(f"OAuth2 token refresh failed: {error_msg}")
        
        token_data = response.json()
        new_token = OAuth2Token(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token", self.token.refresh_token),
            scope=token_data.get("scope")
        )
        
        self.token = new_token
        return new_token
    
    def get_valid_token(self) -> OAuth2Token:
        """
        Get valid access token, refreshing if expired.
        
        Automatically refreshes token if expired or expiring soon.
        
        Returns:
            Valid OAuth2Token
        
        Raises:
            Exception: If no token available or refresh fails
        """
        if not self.token:
            raise Exception("No token available. Call exchange_code_for_token first.")
        
        if self.token.is_expired():
            return self.refresh_token()
        
        return self.token
    
    def revoke_token(self) -> None:
        """
        Revoke current token.
        
        Clears stored token from helper. Note: This does not call the
        provider's revocation endpoint - implement separately if needed.
        """
        self.token = None
        self._code_verifier = None
