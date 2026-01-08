"""Tests for Slack bot event handler.

Tests message events, slash commands, @mentions, and error handling.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

# Note: These tests assume slack_bolt framework
# The actual implementation will use slack_bolt.App


@pytest.fixture
def mock_slack_client():
    """Create mock Slack Web API client."""
    client = Mock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567890.123"})
    client.chat_postEphemeral = AsyncMock(return_value={"ok": True})
    client.users_info = AsyncMock(return_value={
        "ok": True,
        "user": {
            "id": "U123",
            "name": "testuser",
            "profile": {"email": "test@example.com"}
        }
    })
    return client


@pytest.fixture
def mock_query_service():
    """Create mock query service that returns RAG responses."""
    service = Mock()
    service.query = AsyncMock(return_value={
        "answer": "The authentication system uses OAuth2 with JWT tokens.",
        "citations": [
            {
                "source": "confluence",
                "title": "Authentication Architecture",
                "url": "https://example.atlassian.net/wiki/spaces/ENG/pages/123/Auth",
                "snippet": "OAuth2 provides secure token-based authentication..."
            }
        ],
        "conversation_id": "conv-123"
    })
    return service


@pytest.fixture
def slack_bot(mock_slack_client, mock_query_service):
    """Create Slack bot instance with mocked dependencies."""
    from src.integrations.slack_bot import SlackBot
    
    bot = SlackBot(
        slack_client=mock_slack_client,
        query_service=mock_query_service,
        bot_token="xoxb-test-token",
        app_token="xapp-test-token"
    )
    return bot


class TestSlackBotMessageEvents:
    """Test handling of Slack message events."""
    
    async def test_dm_message_triggers_query(self, slack_bot, mock_query_service, mock_slack_client):
        """Direct message to bot should trigger query and return answer."""
        event = {
            "type": "message",
            "channel": "D123ABC",  # DM channel
            "user": "U123",
            "text": "What is our authentication strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Verify query service was called
        mock_query_service.query.assert_called_once()
        call_kwargs = mock_query_service.query.call_args.kwargs
        assert call_kwargs["question"] == "What is our authentication strategy?"
        assert call_kwargs["user_id"] == "U123"
        
        # Verify response was sent
        mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "D123ABC"
        assert "OAuth2" in str(call_kwargs["blocks"])  # Answer in blocks
    
    async def test_public_channel_message_no_mention(self, slack_bot, mock_query_service):
        """Messages in public channel without @mention should be ignored."""
        event = {
            "type": "message",
            "channel": "C123ABC",  # Public channel
            "user": "U123",
            "text": "Random message",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Should not trigger query
        mock_query_service.query.assert_not_called()
    
    async def test_app_mention_in_channel(self, slack_bot, mock_query_service, mock_slack_client):
        """@mention of bot in channel should trigger query."""
        event = {
            "type": "app_mention",
            "channel": "C123ABC",
            "user": "U123",
            "text": "<@BOTID> What is our API strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_app_mention(event)
        
        # Verify query was triggered (without @mention in text)
        mock_query_service.query.assert_called_once()
        call_kwargs = mock_query_service.query.call_args.kwargs
        assert "BOTID" not in call_kwargs["question"]
        assert "API strategy" in call_kwargs["question"]
        
        # Verify response sent
        mock_slack_client.chat_postMessage.assert_called_once()
    
    async def test_thread_reply(self, slack_bot, mock_query_service, mock_slack_client):
        """Reply in thread should maintain thread context."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Can you explain more?",
            "thread_ts": "1234567890.000",  # In thread
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Verify response sent in thread
        mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "1234567890.000"
    
    async def test_bot_message_ignored(self, slack_bot, mock_query_service):
        """Messages from bots should be ignored to prevent loops."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Bot message",
            "bot_id": "B123",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Should not trigger query
        mock_query_service.query.assert_not_called()


class TestSlackBotSlashCommands:
    """Test handling of slash commands."""
    
    async def test_ask_slash_command(self, slack_bot, mock_query_service, mock_slack_client):
        """'/ask' slash command should trigger query."""
        command = {
            "command": "/ask",
            "text": "What are our quarterly goals?",
            "user_id": "U123",
            "channel_id": "C123ABC",
            "response_url": "https://hooks.slack.com/commands/123"
        }
        
        await slack_bot.handle_slash_command(command)
        
        # Verify query triggered
        mock_query_service.query.assert_called_once()
        call_kwargs = mock_query_service.query.call_args.kwargs
        assert call_kwargs["question"] == "What are our quarterly goals?"
        assert call_kwargs["user_id"] == "U123"
    
    async def test_ask_command_in_public_channel_sends_ephemeral(
        self, slack_bot, mock_query_service, mock_slack_client
    ):
        """Slash command in public channel should send ephemeral suggestion to DM."""
        command = {
            "command": "/ask",
            "text": "What are our quarterly goals?",
            "user_id": "U123",
            "channel_id": "C123ABC",  # Public channel
            "channel_name": "general",
            "response_url": "https://hooks.slack.com/commands/123"
        }
        
        await slack_bot.handle_slash_command(command)
        
        # Should send ephemeral message suggesting DM
        mock_slack_client.chat_postEphemeral.assert_called_once()
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        assert call_kwargs["channel"] == "C123ABC"
        assert call_kwargs["user"] == "U123"
        assert "DM" in call_kwargs["text"] or "direct message" in call_kwargs["text"].lower()
    
    async def test_ask_command_with_empty_text(self, slack_bot, mock_query_service, mock_slack_client):
        """Slash command with no text should return help message."""
        command = {
            "command": "/ask",
            "text": "",
            "user_id": "U123",
            "channel_id": "D123ABC",
            "response_url": "https://hooks.slack.com/commands/123"
        }
        
        response = await slack_bot.handle_slash_command(command)
        
        # Should not trigger query
        mock_query_service.query.assert_not_called()
        
        # Should return help text
        assert "usage" in response["text"].lower() or "help" in response["text"].lower()


class TestSlackBotErrorHandling:
    """Test error handling scenarios."""
    
    async def test_query_service_error(self, slack_bot, mock_query_service, mock_slack_client):
        """Query service error should return user-friendly message."""
        mock_query_service.query.side_effect = Exception("Database connection failed")
        
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "What is our strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Should send error message to user
        mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_client.chat_postMessage.call_args.kwargs
        assert "error" in call_kwargs["text"].lower() or "sorry" in call_kwargs["text"].lower()
    
    async def test_slack_api_error(self, slack_bot, mock_query_service, mock_slack_client):
        """Slack API error should be logged but not crash."""
        mock_slack_client.chat_postMessage.side_effect = Exception("Slack API error")
        
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "What is our strategy?",
            "ts": "1234567890.123"
        }
        
        # Should not raise exception
        await slack_bot.handle_message(event)
        
        # Query should still have been called
        mock_query_service.query.assert_called_once()
    
    async def test_malformed_event(self, slack_bot, mock_query_service):
        """Malformed event should be handled gracefully."""
        event = {
            "type": "message",
            # Missing required fields
        }
        
        # Should not raise exception
        await slack_bot.handle_message(event)
        
        # Should not trigger query
        mock_query_service.query.assert_not_called()
    
    async def test_rate_limit_error(self, slack_bot, mock_query_service, mock_slack_client):
        """Rate limit error should be retried with backoff."""
        from slack_sdk.errors import SlackApiError
        
        # Simulate rate limit on first call, success on second
        mock_slack_client.chat_postMessage.side_effect = [
            SlackApiError(
                message="Rate limited",
                response={"ok": False, "error": "rate_limited"}
            ),
            {"ok": True, "ts": "1234567890.123"}
        ]
        
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "What is our strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Should have retried
        assert mock_slack_client.chat_postMessage.call_count == 2


class TestSlackBotUserIdentification:
    """Test user identity resolution."""
    
    async def test_user_email_lookup(self, slack_bot, mock_slack_client):
        """Should lookup user email from Slack API."""
        user_id = "U123"
        
        email = await slack_bot.get_user_email(user_id)
        
        assert email == "test@example.com"
        mock_slack_client.users_info.assert_called_once_with(user=user_id)
    
    async def test_user_email_cache(self, slack_bot, mock_slack_client):
        """Should cache user email to reduce API calls."""
        user_id = "U123"
        
        # Call twice
        await slack_bot.get_user_email(user_id)
        await slack_bot.get_user_email(user_id)
        
        # Should only call API once
        assert mock_slack_client.users_info.call_count == 1
    
    async def test_user_not_found(self, slack_bot, mock_slack_client):
        """Should handle user not found gracefully."""
        mock_slack_client.users_info.return_value = {
            "ok": False,
            "error": "user_not_found"
        }
        
        email = await slack_bot.get_user_email("U999")
        
        assert email is None


class TestSlackBotPrivacySettings:
    """Test privacy and permission checks."""
    
    async def test_private_channel_allowed(self, slack_bot, mock_query_service, mock_slack_client):
        """Private channels should allow bot queries."""
        event = {
            "type": "app_mention",
            "channel": "G123ABC",  # Private channel (starts with G)
            "channel_type": "group",
            "user": "U123",
            "text": "<@BOTID> What is our budget?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_app_mention(event)
        
        # Should process query
        mock_query_service.query.assert_called_once()
        
        # Should post answer (not ephemeral)
        mock_slack_client.chat_postMessage.assert_called_once()
    
    async def test_public_channel_suggests_dm(self, slack_bot, mock_query_service, mock_slack_client):
        """Public channel @mention should suggest using DM."""
        event = {
            "type": "app_mention",
            "channel": "C123ABC",  # Public channel
            "channel_type": "channel",
            "user": "U123",
            "text": "<@BOTID> What is our budget?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_app_mention(event)
        
        # Should send ephemeral suggestion
        mock_slack_client.chat_postEphemeral.assert_called_once()
        call_kwargs = mock_slack_client.chat_postEphemeral.call_args.kwargs
        assert "DM" in call_kwargs["text"] or "direct message" in call_kwargs["text"].lower()
        
        # Should NOT process query in public
        mock_query_service.query.assert_not_called()


class TestSlackBotConversationContext:
    """Test conversation context management."""
    
    async def test_conversation_id_tracking(self, slack_bot, mock_query_service):
        """Should track conversation IDs for context."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "What is our strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Verify conversation tracking
        call_kwargs = mock_query_service.query.call_args.kwargs
        assert "channel_id" in call_kwargs
        assert call_kwargs["channel_id"] == "D123ABC"
    
    async def test_followup_question_uses_conversation(self, slack_bot, mock_query_service):
        """Followup questions should reference previous conversation."""
        # First question
        event1 = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "What is our authentication system?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event1)
        
        # Second question in same channel
        event2 = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Can you explain more about JWT?",
            "ts": "1234567891.456"
        }
        
        await slack_bot.handle_message(event2)
        
        # Should pass conversation context
        assert mock_query_service.query.call_count == 2
        second_call = mock_query_service.query.call_args.kwargs
        assert "conversation_id" in second_call or "channel_id" in second_call
