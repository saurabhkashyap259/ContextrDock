"""Slack bot startup script for ContextDock.

Initializes Slack Bolt app and starts the bot in Socket Mode.
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

from src.integrations.slack_bot import SlackBot, SlackPrivacyHandler
from src.integrations.slack_formatter import SlackFormatter, format_help_message
from src.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Initialize Slack Bolt app
app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


# Mock query service for now
class MockQueryService:
    """Mock query service until real implementation is ready."""
    
    async def query(
        self,
        question: str,
        user_id: str,
        user_email: str = None,
        channel_id: str = None
    ):
        """Mock query method."""
        return {
            "answer": "This is a test response from ContextDock. "
                     "The actual RAG system will provide real answers based on your connected tools.",
            "citations": [
                {
                    "source": "slack",
                    "title": "Example Citation",
                    "url": "https://example.slack.com/archives/C123/p1234567890",
                    "snippet": "This is an example citation from Slack."
                }
            ],
            "conversation_id": "test-conv-123"
        }


# Initialize bot
query_service = MockQueryService()
bot = SlackBot(
    slack_client=app.client,
    query_service=query_service,
    bot_token=os.environ.get("SLACK_BOT_TOKEN"),
    app_token=os.environ.get("SLACK_APP_TOKEN")
)


@app.event("message")
async def handle_message_events(event, say, logger):
    """Handle message events."""
    try:
        await bot.handle_message(event)
    except Exception as e:
        logger.error(f"Error in message handler: {e}", exc_info=True)


@app.event("app_mention")
async def handle_app_mentions(event, say, logger):
    """Handle app mentions (@bot)."""
    try:
        await bot.handle_app_mention(event)
    except Exception as e:
        logger.error(f"Error in app mention handler: {e}", exc_info=True)


@app.command("/ask")
async def handle_ask_command(ack, command, respond, logger):
    """Handle /ask slash command."""
    await ack()
    
    try:
        response = await bot.handle_slash_command(command)
        await respond(response)
    except Exception as e:
        logger.error(f"Error in slash command handler: {e}", exc_info=True)
        await respond({
            "response_type": "ephemeral",
            "text": "Sorry, I encountered an error processing your command."
        })


@app.command("/contextdock")
async def handle_contextdock_command(ack, command, respond):
    """Handle /contextdock command (help and settings)."""
    await ack()
    
    subcommand = command.get("text", "").strip().lower()
    
    if subcommand == "help" or not subcommand:
        blocks = format_help_message()
        await respond({
            "response_type": "ephemeral",
            "blocks": blocks
        })
    elif subcommand == "privacy":
        await respond({
            "response_type": "ephemeral",
            "text": "Privacy settings coming soon. By default, I suggest using DM for sensitive queries in public channels."
        })
    else:
        await respond({
            "response_type": "ephemeral",
            "text": f"Unknown command: {subcommand}. Try `/contextdock help`"
        })


@app.action("feedback_positive")
async def handle_positive_feedback(ack, action, logger):
    """Handle positive feedback button."""
    await ack()
    logger.info(f"Positive feedback: {action.get('value')}")


@app.action("feedback_negative")
async def handle_negative_feedback(ack, action, logger):
    """Handle negative feedback button."""
    await ack()
    logger.info(f"Negative feedback: {action.get('value')}")


@app.event("app_home_opened")
async def handle_app_home_opened(event, client, logger):
    """Handle App Home tab opened."""
    try:
        user_id = event["user"]
        
        # Publish home view
        await client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "👋 Welcome to ContextDock"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Your intelligent workplace assistant*\n\n"
                                   "I can help you find information across all your connected tools. "
                                   "Just send me a message or use `/ask <your question>`."
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Quick Tips:*\n"
                                   "• Be specific in your questions\n"
                                   "• I respect your access permissions\n"
                                   "• Use DM for confidential queries\n"
                                   "• Click citations to see sources"
                        }
                    }
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error publishing home view: {e}", exc_info=True)


async def main():
    """Start the Slack bot."""
    logger.info("Starting ContextDock Slack Bot...")
    
    # Verify tokens are set
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    
    if not bot_token or not app_token:
        logger.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set")
        sys.exit(1)
    
    logger.info("Slack tokens verified")
    
    # Start Socket Mode handler
    handler = AsyncSocketModeHandler(app, app_token)
    
    logger.info("Connecting to Slack...")
    await handler.start_async()
    
    logger.info("✅ ContextDock Slack Bot is running!")


if __name__ == "__main__":
    import asyncio
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down ContextDock Slack Bot...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
