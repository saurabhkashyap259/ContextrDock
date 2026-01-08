"""Tests for Slack bot privacy logic.

Tests ephemeral responses, DM suggestions, and privacy enforcement.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_slack_client():
    """Create mock Slack client."""
    client = Mock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "123.456"})
    client.chat_postEphemeral = AsyncMock(return_value={"ok": True})
    client.conversations_info = AsyncMock()
    return client


@pytest.fixture
def slack_privacy():
    """Create Slack privacy handler instance."""
    from src.integrations.slack_bot import SlackPrivacyHandler
    return SlackPrivacyHandler()


class TestChannelTypeDetection:
    """Test detection of channel types (public/private/DM)."""
    
    async def test_detect_dm_channel(self, slack_privacy):
        """Should detect DM channels (start with D)."""
        channel_id = "D123ABC456"
        
        is_dm = await slack_privacy.is_dm_channel(channel_id)
        
        assert is_dm is True
    
    async def test_detect_public_channel(self, slack_privacy, mock_slack_client):
        """Should detect public channels (start with C)."""
        channel_id = "C123ABC456"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {
                "id": channel_id,
                "is_private": False,
                "is_channel": True
            }
        }
        
        is_public = await slack_privacy.is_public_channel(channel_id, mock_slack_client)
        
        assert is_public is True
    
    async def test_detect_private_channel(self, slack_privacy, mock_slack_client):
        """Should detect private channels (start with G or private flag)."""
        channel_id = "G123ABC456"  # Private channel
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {
                "id": channel_id,
                "is_private": True,
                "is_group": True
            }
        }
        
        is_private = await slack_privacy.is_private_channel(channel_id, mock_slack_client)
        
        assert is_private is True
    
    async def test_detect_mpim_channel(self, slack_privacy):
        """Should detect multi-party IM channels (start with G, MPIM)."""
        channel_id = "G123MPIM"
        
        # MPIMs are treated as private
        is_dm_like = await slack_privacy.is_dm_or_private(channel_id)
        
        assert is_dm_like is True


class TestPrivacyDecisions:
    """Test privacy decision logic."""
    
    async def test_dm_allows_full_response(self, slack_privacy):
        """DM channels should allow full responses."""
        channel_id = "D123ABC"
        user_id = "U123"
        
        decision = await slack_privacy.should_respond_publicly(channel_id, user_id)
        
        assert decision["respond_publicly"] is True
        assert decision["suggestion_needed"] is False
    
    async def test_private_channel_allows_full_response(self, slack_privacy, mock_slack_client):
        """Private channels should allow full responses."""
        channel_id = "G123ABC"
        user_id = "U123"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {"is_private": True}
        }
        
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, slack_client=mock_slack_client
        )
        
        assert decision["respond_publicly"] is True
        assert decision["suggestion_needed"] is False
    
    async def test_public_channel_suggests_dm(self, slack_privacy, mock_slack_client):
        """Public channels should suggest using DM."""
        channel_id = "C123ABC"  # Public channel
        user_id = "U123"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {"is_private": False, "is_channel": True}
        }
        
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, slack_client=mock_slack_client
        )
        
        assert decision["respond_publicly"] is False
        assert decision["suggestion_needed"] is True
        assert "reason" in decision
        assert "public" in decision["reason"].lower()
    
    async def test_thread_in_public_channel(self, slack_privacy, mock_slack_client):
        """Threads in public channels should still suggest DM."""
        channel_id = "C123ABC"
        user_id = "U123"
        thread_ts = "1234567890.123"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {"is_private": False}
        }
        
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, thread_ts=thread_ts, slack_client=mock_slack_client
        )
        
        # Even in thread, public channel should suggest DM
        assert decision["respond_publicly"] is False
        assert decision["suggestion_needed"] is True


class TestEphemeralResponses:
    """Test ephemeral response handling."""
    
    async def test_send_ephemeral_dm_suggestion(self, slack_privacy, mock_slack_client):
        """Should send ephemeral message suggesting DM."""
        channel_id = "C123ABC"
        user_id = "U123"
        
        await slack_privacy.send_dm_suggestion(channel_id, user_id, mock_slack_client)
        
        # Should call chat_postEphemeral
        mock_slack_client.chat_postEphemeral.assert_called_once()
        
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        assert call_kwargs["channel"] == channel_id
        assert call_kwargs["user"] == user_id
        
        # Message should mention DM
        message_text = call_kwargs.get("text", "") + str(call_kwargs.get("blocks", []))
        assert "DM" in message_text or "direct message" in message_text.lower()
    
    async def test_ephemeral_message_only_to_user(self, slack_privacy, mock_slack_client):
        """Ephemeral messages should only be visible to the specific user."""
        channel_id = "C123ABC"
        user_id = "U123"
        
        await slack_privacy.send_dm_suggestion(channel_id, user_id, mock_slack_client)
        
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        
        # Must specify user for ephemeral
        assert "user" in call_kwargs
        assert call_kwargs["user"] == user_id
    
    async def test_ephemeral_includes_deep_link(self, slack_privacy, mock_slack_client):
        """Ephemeral suggestion should include link to DM bot."""
        channel_id = "C123ABC"
        user_id = "U123"
        bot_user_id = "U_BOT123"
        
        await slack_privacy.send_dm_suggestion(
            channel_id, user_id, mock_slack_client, bot_user_id=bot_user_id
        )
        
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        message_content = str(call_kwargs)
        
        # Should have deep link or mention
        assert f"<@{bot_user_id}>" in message_content or \
               f"slack://user?team={{team_id}}&id={bot_user_id}" in message_content


class TestPrivacySettings:
    """Test user privacy preferences."""
    
    async def test_user_can_override_privacy_settings(self, slack_privacy):
        """Users should be able to opt-in to public responses."""
        user_id = "U123"
        channel_id = "C123ABC"  # Public channel
        
        # User opts in to public responses
        slack_privacy.set_user_preference(user_id, allow_public_responses=True)
        
        decision = await slack_privacy.should_respond_publicly(channel_id, user_id)
        
        # Should allow public response if user opted in
        assert decision["respond_publicly"] is True
    
    async def test_default_privacy_is_restrictive(self, slack_privacy):
        """Default should be restrictive (suggest DM in public channels)."""
        user_id = "U_NEW"  # User with no preferences set
        channel_id = "C123ABC"  # Public channel
        
        decision = await slack_privacy.should_respond_publicly(channel_id, user_id)
        
        # Should default to suggesting DM
        assert decision["respond_publicly"] is False
        assert decision["suggestion_needed"] is True
    
    async def test_workspace_admin_can_set_default_policy(self, slack_privacy):
        """Workspace admins should be able to set default privacy policy."""
        workspace_id = "T123"
        
        # Admin sets policy: allow public responses
        slack_privacy.set_workspace_policy(workspace_id, allow_public_responses=True)
        
        user_id = "U123"
        channel_id = "C123ABC"
        
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, workspace_id=workspace_id
        )
        
        # Should respect workspace policy
        assert decision["respond_publicly"] is True


class TestSensitiveDataProtection:
    """Test sensitive data handling in public channels."""
    
    async def test_detect_sensitive_query(self, slack_privacy):
        """Should detect potentially sensitive queries."""
        sensitive_queries = [
            "What is the database password?",
            "Show me the API keys",
            "Who has access to production?",
            "What is our budget for next quarter?",
            "Employee salary information"
        ]
        
        for query in sensitive_queries:
            is_sensitive = await slack_privacy.is_potentially_sensitive(query)
            assert is_sensitive is True, f"Should detect sensitive query: {query}"
    
    async def test_sensitive_query_forces_dm(self, slack_privacy, mock_slack_client):
        """Sensitive queries should always suggest DM, even with user opt-in."""
        user_id = "U123"
        channel_id = "C123ABC"  # Public channel
        
        # User opted in to public responses
        slack_privacy.set_user_preference(user_id, allow_public_responses=True)
        
        query = "What is the database password?"
        
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, query_text=query
        )
        
        # Should override user preference for sensitive queries
        assert decision["respond_publicly"] is False
        assert decision["suggestion_needed"] is True
        assert "sensitive" in decision.get("reason", "").lower()
    
    async def test_non_sensitive_query_allowed(self, slack_privacy):
        """Non-sensitive queries should not trigger warnings."""
        safe_queries = [
            "How does our authentication work?",
            "What is our API design?",
            "Tell me about our deployment process"
        ]
        
        for query in safe_queries:
            is_sensitive = await slack_privacy.is_potentially_sensitive(query)
            assert is_sensitive is False, f"Should not flag as sensitive: {query}"


class TestChannelMembershipChecks:
    """Test checking if bot is in channel."""
    
    async def test_bot_not_in_channel(self, slack_privacy, mock_slack_client):
        """Should detect when bot is not in channel."""
        channel_id = "C123ABC"
        bot_user_id = "U_BOT"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {
                "id": channel_id,
                "is_member": False
            }
        }
        
        is_member = await slack_privacy.bot_is_channel_member(
            channel_id, bot_user_id, mock_slack_client
        )
        
        assert is_member is False
    
    async def test_bot_in_channel(self, slack_privacy, mock_slack_client):
        """Should detect when bot is in channel."""
        channel_id = "C123ABC"
        bot_user_id = "U_BOT"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {
                "id": channel_id,
                "is_member": True
            }
        }
        
        is_member = await slack_privacy.bot_is_channel_member(
            channel_id, bot_user_id, mock_slack_client
        )
        
        assert is_member is True


class TestPrivacyLogging:
    """Test privacy decision logging."""
    
    async def test_log_privacy_decision(self, slack_privacy, mock_slack_client):
        """Should log privacy decisions for audit."""
        channel_id = "C123ABC"
        user_id = "U123"
        
        with patch('src.integrations.slack_bot.logger') as mock_logger:
            decision = await slack_privacy.should_respond_publicly(
                channel_id, user_id, slack_client=mock_slack_client
            )
            
            # Should log the decision
            assert mock_logger.info.called or mock_logger.debug.called
    
    async def test_log_sensitive_query_detection(self, slack_privacy):
        """Should log when sensitive queries are detected."""
        query = "What is the production database password?"
        
        with patch('src.integrations.slack_bot.logger') as mock_logger:
            is_sensitive = await slack_privacy.is_potentially_sensitive(query)
            
            if is_sensitive:
                # Should log sensitive query detection
                assert mock_logger.warning.called or mock_logger.info.called


class TestRateLimitingPrivacy:
    """Test rate limiting combined with privacy."""
    
    async def test_rate_limited_user_in_public_channel(self, slack_privacy, mock_slack_client):
        """Rate-limited users should still get ephemeral suggestions."""
        user_id = "U123"
        channel_id = "C123ABC"
        
        # Simulate rate limit
        slack_privacy.mark_user_rate_limited(user_id)
        
        # Should still suggest DM
        await slack_privacy.send_dm_suggestion(channel_id, user_id, mock_slack_client)
        
        mock_slack_client.chat_postEphemeral.assert_called_once()
        
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        message = str(call_kwargs)
        
        # Should mention both rate limit and privacy
        assert "rate" in message.lower() or "too many" in message.lower()


class TestPrivacyExceptions:
    """Test exceptional cases in privacy handling."""
    
    async def test_handle_slack_api_error_gracefully(self, slack_privacy, mock_slack_client):
        """Should handle Slack API errors when checking channel info."""
        channel_id = "C123ABC"
        user_id = "U123"
        
        mock_slack_client.conversations_info.return_value = {
            "ok": False,
            "error": "channel_not_found"
        }
        
        # Should not crash
        decision = await slack_privacy.should_respond_publicly(
            channel_id, user_id, slack_client=mock_slack_client
        )
        
        # Should default to safe behavior (suggest DM)
        assert decision["respond_publicly"] is False
    
    async def test_malformed_channel_id(self, slack_privacy):
        """Should handle malformed channel IDs."""
        channel_id = "INVALID"
        user_id = "U123"
        
        # Should not crash
        decision = await slack_privacy.should_respond_publicly(channel_id, user_id)
        
        # Should default to safe behavior
        assert isinstance(decision, dict)
        assert "respond_publicly" in decision


class TestPrivacyHelperMethods:
    """Test helper methods for privacy logic."""
    
    def test_channel_id_prefix_detection(self, slack_privacy):
        """Should correctly identify channel type by prefix."""
        assert slack_privacy.is_dm_prefix("D123ABC") is True
        assert slack_privacy.is_dm_prefix("C123ABC") is False
        
        assert slack_privacy.is_public_prefix("C123ABC") is True
        assert slack_privacy.is_public_prefix("G123ABC") is False
        
        assert slack_privacy.is_private_prefix("G123ABC") is True
        assert slack_privacy.is_private_prefix("C123ABC") is False
    
    def test_redact_sensitive_content(self, slack_privacy):
        """Should redact sensitive information from logs."""
        text = "The password is supersecret123 and the API key is sk-abc123xyz"
        
        redacted = slack_privacy.redact_sensitive_content(text)
        
        # Should not contain actual secrets
        assert "supersecret123" not in redacted
        assert "sk-abc123xyz" not in redacted
        
        # Should have redaction markers
        assert "[REDACTED]" in redacted or "***" in redacted
