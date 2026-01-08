"""US4 Scenario 1: DM Bot Query

Tests that users can ask questions via DM and receive formatted answers with citations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.integrations.slack_bot import SlackBot
from src.integrations.slack_formatter import SlackFormatter


@pytest.fixture
def mock_slack_client():
    """Mock Slack client."""
    client = Mock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "123.456"})
    client.users_info = AsyncMock(return_value={
        "ok": True,
        "user": {"profile": {"email": "user@example.com"}}
    })
    return client


@pytest.fixture
def mock_query_service():
    """Mock query service."""
    service = Mock()
    service.query = AsyncMock(return_value={
        "answer": "Our authentication system uses **OAuth2** with JWT tokens for secure access.",
        "citations": [
            {
                "source": "confluence",
                "title": "Auth Architecture",
                "url": "https://example.atlassian.net/wiki/auth",
                "snippet": "OAuth2 implementation details"
            },
            {
                "source": "github",
                "title": "auth-service/README.md",
                "url": "https://github.com/org/auth-service",
                "snippet": "JWT token configuration"
            }
        ],
        "conversation_id": "conv-test-123"
    })
    return service


@pytest.fixture
def slack_bot(mock_slack_client, mock_query_service):
    """Create SlackBot instance."""
    return SlackBot(
        slack_client=mock_slack_client,
        query_service=mock_query_service,
        bot_token="xoxb-test",
        app_token="xapp-test"
    )


class TestDMBotQuery:
    """Test DM interaction with bot."""
    
    async def test_send_dm_question_receive_answer(
        self, slack_bot, mock_slack_client, mock_query_service
    ):
        """User sends DM question and receives formatted answer."""
        event = {
            "type": "message",
            "channel": "D123ABC",  # DM
            "user": "U123",
            "text": "How does our authentication system work?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Verify query service called
        mock_query_service.query.assert_called_once()
        call_args = mock_query_service.query.call_args.kwargs
        assert call_args["question"] == "How does our authentication system work?"
        assert call_args["user_id"] == "U123"
        
        # Verify response sent
        mock_slack_client.chat_postMessage.assert_called_once()
        response_args = mock_slack_client.chat_postMessage.call_args.kwargs
        assert response_args["channel"] == "D123ABC"
        assert "blocks" in response_args
        
        # Verify blocks contain answer
        blocks_str = str(response_args["blocks"])
        assert "OAuth2" in blocks_str
        assert "JWT" in blocks_str
    
    async def test_dm_response_includes_citations(
        self, slack_bot, mock_slack_client, mock_query_service
    ):
        """DM response should include formatted citations."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Tell me about auth",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        response_args = mock_slack_client.chat_postMessage.call_args.kwargs
        blocks = response_args["blocks"]
        
        # Check for citation blocks
        blocks_str = str(blocks)
        assert "Auth Architecture" in blocks_str
        assert "auth-service/README.md" in blocks_str
        assert "https://example.atlassian.net" in blocks_str
        assert "https://github.com" in blocks_str
    
    async def test_dm_response_has_clickable_links(self, slack_bot, mock_slack_client):
        """Citations should have clickable Slack-formatted links."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Auth info?",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        response_args = mock_slack_client.chat_postMessage.call_args.kwargs
        blocks = response_args["blocks"]
        blocks_str = str(blocks)
        
        # Slack link format: <URL|Text> or just URL
        assert "<https://" in blocks_str or "https://" in blocks_str
    
    async def test_followup_question_in_thread(
        self, slack_bot, mock_slack_client, mock_query_service
    ):
        """Followup questions should stay in thread."""
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Can you explain JWT tokens?",
            "thread_ts": "1234567890.000",  # In thread
            "ts": "1234567891.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Response should be in thread
        response_args = mock_slack_client.chat_postMessage.call_args.kwargs
        assert response_args["thread_ts"] == "1234567890.000"
    
    async def test_error_handling_in_dm(
        self, slack_bot, mock_slack_client, mock_query_service
    ):
        """Errors should be formatted user-friendly."""
        mock_query_service.query.side_effect = Exception("Database error")
        
        event = {
            "type": "message",
            "channel": "D123ABC",
            "user": "U123",
            "text": "Question",
            "ts": "1234567890.123"
        }
        
        await slack_bot.handle_message(event)
        
        # Should still send a message (error message)
        mock_slack_client.chat_postMessage.assert_called_once()
        response_args = mock_slack_client.chat_postMessage.call_args.kwargs
        
        # Should be user-friendly, not technical
        text = str(response_args.get("blocks", []))
        assert "sorry" in text.lower() or "error" in text.lower()


class TestSlackFormatterIntegration:
    """Test SlackFormatter integration."""
    
    def test_format_complete_response(self):
        """Test complete response formatting."""
        formatter = SlackFormatter()
        
        answer_data = {
            "answer": "OAuth2 authentication with **JWT** tokens.",
            "citations": [
                {
                    "source": "confluence",
                    "title": "Auth Docs",
                    "url": "https://example.com/docs",
                    "snippet": "Implementation details"
                }
            ],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer_data)
        
        # Should have multiple blocks
        assert len(blocks) >= 3  # Answer, divider, citation
        
        # Check block types
        assert any(b["type"] == "section" for b in blocks)
        assert any(b["type"] == "divider" for b in blocks)
        assert any(b["type"] == "context" for b in blocks)
    
    def test_block_structure_valid(self):
        """Blocks should follow Slack schema."""
        formatter = SlackFormatter()
        
        answer_data = {
            "answer": "Test answer",
            "citations": [],
            "conversation_id": "conv-123"
        }
        
        blocks = formatter.format_answer(answer_data)
        
        for block in blocks:
            assert "type" in block
            assert block["type"] in ["section", "divider", "context", "header", "actions"]
