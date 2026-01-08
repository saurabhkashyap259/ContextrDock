"""US4 Scenario 2: Slash Command with Ephemeral Response

Tests /ask slash command in public channels sends ephemeral DM suggestion.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.integrations.slack_bot import SlackBot


@pytest.fixture
def mock_slack_client():
    """Mock Slack client."""
    client = Mock()
    client.chat_postEphemeral = AsyncMock(return_value={"ok": True})
    client.conversations_info = AsyncMock(return_value={
        "ok": True,
        "channel": {"is_private": False, "is_channel": True}
    })
    return client


@pytest.fixture
def slack_bot(mock_slack_client):
    """Create SlackBot instance."""
    query_service = Mock()
    return SlackBot(
        slack_client=mock_slack_client,
        query_service=query_service,
        bot_token="xoxb-test",
        app_token="xapp-test"
    )


class TestSlashCommandPrivacy:
    """Test /ask slash command privacy enforcement."""
    
    async def test_ask_in_public_channel_sends_ephemeral(
        self, slack_bot, mock_slack_client
    ):
        """'/ask' in public channel should send ephemeral suggestion."""
        command = {
            "command": "/ask",
            "text": "What are our quarterly goals?",
            "user_id": "U123",
            "channel_id": "C123ABC",  # Public channel
            "channel_name": "general"
        }
        
        await slack_bot.handle_slash_command(command)
        
        # Should send ephemeral message
        mock_slack_client.chat_postEphemeral.assert_called_once()
        call_args = mock_slack_client.chat_postEphemeral.call_args.kwargs
        
        assert call_args["channel"] == "C123ABC"
        assert call_args["user"] == "U123"
        
        # Message should suggest DM
        message = call_args.get("text", "") + str(call_args.get("blocks", []))
        assert "DM" in message or "direct message" in message.lower()
    
    async def test_ask_with_empty_text_shows_help(self, slack_bot):
        """'/ask' with no text should show help."""
        command = {
            "command": "/ask",
            "text": "",
            "user_id": "U123",
            "channel_id": "D123ABC"
        }
        
        response = await slack_bot.handle_slash_command(command)
        
        # Should return help
        assert "help" in str(response).lower() or "usage" in str(response).lower()
