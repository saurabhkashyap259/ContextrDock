"""US4 Scenario 3: @Mention Privacy Enforcement

Tests @mention in public channel suggests DM, works in private channels.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.integrations.slack_bot import SlackBot


@pytest.fixture
def mock_slack_client():
    """Mock Slack client."""
    client = Mock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "123.456"})
    client.chat_postEphemeral = AsyncMock(return_value={"ok": True})
    client.conversations_info = AsyncMock()
    return client


@pytest.fixture
def slack_bot(mock_slack_client):
    """Create SlackBot instance."""
    query_service = Mock()
    query_service.query = AsyncMock(return_value={
        "answer": "Test answer",
        "citations": [],
        "conversation_id": "conv-123"
    })
    return SlackBot(
        slack_client=mock_slack_client,
        query_service=query_service,
        bot_token="xoxb-test",
        app_token="xapp-test"
    )


class TestAppMentionPrivacy:
    """Test @mention privacy enforcement."""
    
    async def test_mention_in_public_channel_suggests_dm(
        self, slack_bot, mock_slack_client
    ):
        """@mention in public channel should suggest DM."""
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {"is_private": False, "is_channel": True}
        }
        
        event = {
            "type": "app_mention",
            "channel": "C123ABC",  # Public
            "user": "U123",
            "text": "<@BOTID> What is our budget?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_app_mention(event)
        
        # Should send ephemeral suggestion
        mock_slack_client.chat_postEphemeral.assert_called_once()
        
        # Should NOT post public message
        mock_slack_client.chat_postMessage.assert_not_called()
    
    async def test_mention_in_private_channel_responds(
        self, slack_bot, mock_slack_client
    ):
        """@mention in private channel should respond normally."""
        mock_slack_client.conversations_info.return_value = {
            "ok": True,
            "channel": {"is_private": True}
        }
        
        event = {
            "type": "app_mention",
            "channel": "G123ABC",  # Private
            "user": "U123",
            "text": "<@BOTID> What is our strategy?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_app_mention(event)
        
        # Should post message
        mock_slack_client.chat_postMessage.assert_called_once()
        
        # Should NOT send ephemeral
        mock_slack_client.chat_postEphemeral.assert_not_called()
