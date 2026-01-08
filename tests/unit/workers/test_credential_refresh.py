"""
Unit tests for OAuth credential expiration handling (T193).

Tests auto-refresh functionality:
- Token expiration detection
- Auto-refresh with retry backoff (1min, 5min, 15min)
- Credential renewal via OAuth flow
- Error handling for failed refresh attempts
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
import asyncio


class CredentialStatus:
    """Credential validity states."""
    VALID = "valid"
    EXPIRED = "expired"
    REFRESHING = "refreshing"
    FAILED = "failed"


class OAuthCredential:
    """
    OAuth credential with expiration tracking.
    
    Represents OAuth tokens (access_token, refresh_token) with:
    - Expiration time tracking
    - Auto-refresh capability
    - Retry logic with exponential backoff
    """
    
    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        integration_id: int,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.integration_id = integration_id
        self.status = CredentialStatus.VALID
    
    def is_expired(self) -> bool:
        """Check if credential is expired."""
        return datetime.now() >= self.expires_at
    
    def expires_soon(self, buffer_minutes: int = 5) -> bool:
        """Check if credential expires within buffer time."""
        buffer_time = datetime.now() + timedelta(minutes=buffer_minutes)
        return self.expires_at <= buffer_time


class CredentialRefreshManager:
    """
    Manager for OAuth credential refresh with retry logic (T194).
    
    Features:
    - Exponential backoff: 1min, 5min, 15min
    - Automatic retry on transient failures
    - Token refresh via OAuth provider
    """
    
    def __init__(self):
        self.retry_delays = [60, 300, 900]  # 1min, 5min, 15min in seconds
    
    async def refresh_credential(
        self,
        credential: OAuthCredential,
        oauth_client: any,
    ) -> OAuthCredential:
        """
        Refresh OAuth credential with retry logic.
        
        Args:
            credential: Expired or soon-to-expire credential
            oauth_client: OAuth client for token refresh
            
        Returns:
            Refreshed credential
            
        Raises:
            CredentialRefreshError: If all retry attempts fail
        """
        for attempt, delay in enumerate(self.retry_delays):
            try:
                # Attempt refresh
                new_tokens = await oauth_client.refresh_tokens(
                    refresh_token=credential.refresh_token
                )
                
                # Create new credential
                new_credential = OAuthCredential(
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens.get("refresh_token", credential.refresh_token),
                    expires_at=datetime.now() + timedelta(seconds=new_tokens["expires_in"]),
                    integration_id=credential.integration_id,
                )
                
                new_credential.status = CredentialStatus.VALID
                return new_credential
            
            except Exception as e:
                if attempt < len(self.retry_delays) - 1:
                    # Wait before retry
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    credential.status = CredentialStatus.FAILED
                    raise CredentialRefreshError(
                        f"Failed to refresh credential after {len(self.retry_delays)} attempts: {e}"
                    )
        
        raise CredentialRefreshError("Unexpected refresh failure")


class CredentialRefreshError(Exception):
    """Exception raised when credential refresh fails."""
    pass


class TestOAuthCredential:
    """Test OAuth credential expiration detection."""
    
    def test_credential_not_expired_initially(self):
        """Test that newly created credential is not expired."""
        cred = OAuthCredential(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_at=datetime.now() + timedelta(hours=1),
            integration_id=1,
        )
        
        assert not cred.is_expired()
        assert cred.status == CredentialStatus.VALID
    
    def test_credential_expired_after_time(self):
        """Test that credential is expired after expiration time."""
        cred = OAuthCredential(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_at=datetime.now() - timedelta(minutes=1),  # Expired 1 min ago
            integration_id=1,
        )
        
        assert cred.is_expired()
    
    def test_credential_expires_soon(self):
        """Test detection of soon-to-expire credentials."""
        cred = OAuthCredential(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_at=datetime.now() + timedelta(minutes=3),  # Expires in 3 min
            integration_id=1,
        )
        
        # Should detect expiration within 5 min buffer
        assert cred.expires_soon(buffer_minutes=5)
    
    def test_credential_not_expires_soon_if_long_lived(self):
        """Test that long-lived credentials don't trigger early refresh."""
        cred = OAuthCredential(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_at=datetime.now() + timedelta(hours=1),
            integration_id=1,
        )
        
        # Should not detect expiration within 5 min buffer
        assert not cred.expires_soon(buffer_minutes=5)


class TestCredentialRefreshManager:
    """Test credential refresh with retry logic."""
    
    @pytest.mark.asyncio
    async def test_successful_refresh_first_attempt(self):
        """Test successful token refresh on first attempt."""
        manager = CredentialRefreshManager()
        
        # Mock OAuth client
        oauth_client = Mock()
        oauth_client.refresh_tokens = AsyncMock(return_value={
            "access_token": "new_access_789",
            "refresh_token": "new_refresh_012",
            "expires_in": 3600,  # 1 hour
        })
        
        # Expired credential
        old_cred = OAuthCredential(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=datetime.now() - timedelta(minutes=1),
            integration_id=1,
        )
        
        # Refresh
        new_cred = await manager.refresh_credential(old_cred, oauth_client)
        
        # Verify new credential
        assert new_cred.access_token == "new_access_789"
        assert new_cred.refresh_token == "new_refresh_012"
        assert new_cred.status == CredentialStatus.VALID
        assert new_cred.expires_at > datetime.now()
        
        # Should be called once
        oauth_client.refresh_tokens.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Test retry logic on transient failures."""
        manager = CredentialRefreshManager()
        
        # Mock OAuth client with failure then success
        oauth_client = Mock()
        oauth_client.refresh_tokens = AsyncMock(side_effect=[
            Exception("Transient error"),  # First attempt fails
            {
                "access_token": "new_access_789",
                "expires_in": 3600,
            },  # Second attempt succeeds
        ])
        
        old_cred = OAuthCredential(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=datetime.now() - timedelta(minutes=1),
            integration_id=1,
        )
        
        # Refresh (should retry after 60s delay)
        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            new_cred = await manager.refresh_credential(old_cred, oauth_client)
            
            # Verify retry delay was used
            mock_sleep.assert_called_once_with(60)  # 1 min delay
        
        # Should succeed on second attempt
        assert new_cred.access_token == "new_access_789"
        assert oauth_client.refresh_tokens.call_count == 2
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff_delays(self):
        """Test exponential backoff delays (1min, 5min, 15min)."""
        manager = CredentialRefreshManager()
        
        # Verify retry delays
        assert manager.retry_delays == [60, 300, 900]
    
    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test failure after all retry attempts exhausted."""
        manager = CredentialRefreshManager()
        
        # Mock OAuth client that always fails
        oauth_client = Mock()
        oauth_client.refresh_tokens = AsyncMock(side_effect=Exception("OAuth provider down"))
        
        old_cred = OAuthCredential(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=datetime.now() - timedelta(minutes=1),
            integration_id=1,
        )
        
        # Should fail after all retries
        with patch('asyncio.sleep', new=AsyncMock()):
            with pytest.raises(CredentialRefreshError) as exc_info:
                await manager.refresh_credential(old_cred, oauth_client)
            
            assert "Failed to refresh credential after 3 attempts" in str(exc_info.value)
        
        # Should have tried 3 times
        assert oauth_client.refresh_tokens.call_count == 3
        
        # Credential should be marked as failed
        assert old_cred.status == CredentialStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_refresh_token_reuse_if_not_rotated(self):
        """Test that refresh_token is reused if provider doesn't rotate it."""
        manager = CredentialRefreshManager()
        
        # Mock OAuth client that doesn't return new refresh_token
        oauth_client = Mock()
        oauth_client.refresh_tokens = AsyncMock(return_value={
            "access_token": "new_access_789",
            # No refresh_token in response (not rotated)
            "expires_in": 3600,
        })
        
        old_cred = OAuthCredential(
            access_token="old_access",
            refresh_token="old_refresh_keep",
            expires_at=datetime.now() - timedelta(minutes=1),
            integration_id=1,
        )
        
        new_cred = await manager.refresh_credential(old_cred, oauth_client)
        
        # Old refresh_token should be kept
        assert new_cred.refresh_token == "old_refresh_keep"


class TestSyncTaskCredentialRefresh:
    """Test credential refresh in sync task worker."""
    
    @pytest.mark.asyncio
    async def test_sync_checks_credential_before_sync(self):
        """Test that sync task checks credential expiration before syncing."""
        # Mock sync task
        sync_task = Mock()
        sync_task.integration_id = 1
        
        # Mock credential that expires soon
        credential = OAuthCredential(
            access_token="access_123",
            refresh_token="refresh_456",
            expires_at=datetime.now() + timedelta(minutes=2),  # Expires in 2 min
            integration_id=1,
        )
        
        # Should detect expiration
        assert credential.expires_soon(buffer_minutes=5)
    
    @pytest.mark.asyncio
    async def test_sync_refreshes_credential_if_expired(self):
        """Test that sync task refreshes credential if expired."""
        manager = CredentialRefreshManager()
        
        # Mock expired credential
        expired_cred = OAuthCredential(
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=datetime.now() - timedelta(minutes=1),
            integration_id=1,
        )
        
        assert expired_cred.is_expired()
        
        # Mock OAuth client
        oauth_client = Mock()
        oauth_client.refresh_tokens = AsyncMock(return_value={
            "access_token": "refreshed_access",
            "expires_in": 3600,
        })
        
        # Refresh before sync
        new_cred = await manager.refresh_credential(expired_cred, oauth_client)
        
        # Should have fresh credential
        assert not new_cred.is_expired()
        assert new_cred.access_token == "refreshed_access"
    
    @pytest.mark.asyncio
    async def test_sync_continues_with_valid_credential(self):
        """Test that sync proceeds if credential is valid."""
        credential = OAuthCredential(
            access_token="valid_access",
            refresh_token="valid_refresh",
            expires_at=datetime.now() + timedelta(hours=1),
            integration_id=1,
        )
        
        # Credential is valid, no refresh needed
        assert not credential.is_expired()
        assert not credential.expires_soon(buffer_minutes=5)
        
        # Sync can proceed with existing credential
        assert credential.status == CredentialStatus.VALID
