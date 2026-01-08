"""Slack bot integration for ContextDock.

Handles message events, slash commands, and app mentions with privacy enforcement.
Uses Slack Bolt framework for event handling.
"""

import logging
import re
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)


class SlackPrivacyHandler:
    """Handle privacy decisions and enforcement."""
    
    def __init__(self):
        """Initialize privacy handler."""
        self.user_preferences: Dict[str, Dict[str, Any]] = {}
        self.workspace_policies: Dict[str, Dict[str, Any]] = {}
        self._sensitive_patterns = [
            r'password',
            r'api[_\s]key',
            r'secret',
            r'token',
            r'credential',
            r'salary',
            r'budget',
            r'confidential'
        ]
    
    async def is_dm_channel(self, channel_id: str) -> bool:
        """Check if channel is a DM."""
        return channel_id.startswith('D')
    
    async def is_dm_or_private(self, channel_id: str) -> bool:
        """Check if channel is DM or private (G prefix)."""
        return channel_id.startswith('D') or channel_id.startswith('G')
    
    async def is_public_channel(
        self,
        channel_id: str,
        slack_client: Any
    ) -> bool:
        """Check if channel is public."""
        try:
            result = await slack_client.conversations_info(channel=channel_id)
            if result.get("ok"):
                channel = result.get("channel", {})
                return not channel.get("is_private", False) and channel.get("is_channel", False)
        except Exception as e:
            logger.error(f"Error checking channel info: {e}")
        
        return False  # Default to safe (private)
    
    async def is_private_channel(
        self,
        channel_id: str,
        slack_client: Any
    ) -> bool:
        """Check if channel is private."""
        try:
            result = await slack_client.conversations_info(channel=channel_id)
            if result.get("ok"):
                return result.get("channel", {}).get("is_private", False)
        except Exception as e:
            logger.error(f"Error checking channel info: {e}")
        
        return True  # Default to safe (assume private)
    
    async def should_respond_publicly(
        self,
        channel_id: str,
        user_id: str,
        query_text: Optional[str] = None,
        thread_ts: Optional[str] = None,
        workspace_id: Optional[str] = None,
        slack_client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Decide if response should be public or suggest DM.
        
        Args:
            channel_id: Slack channel ID
            user_id: Slack user ID
            query_text: Query text for sensitivity check
            thread_ts: Thread timestamp if in thread
            workspace_id: Workspace ID for policy check
            slack_client: Slack client for API calls
            
        Returns:
            Dict with respond_publicly (bool), suggestion_needed (bool), reason (str)
        """
        # Always allow DM and private channels
        if channel_id.startswith('D') or channel_id.startswith('G'):
            return {
                "respond_publicly": True,
                "suggestion_needed": False,
                "reason": "DM or private channel"
            }
        
        # Check if sensitive query
        if query_text and await self.is_potentially_sensitive(query_text):
            return {
                "respond_publicly": False,
                "suggestion_needed": True,
                "reason": "Potentially sensitive query in public channel"
            }
        
        # Check user preference
        user_pref = self.user_preferences.get(user_id, {})
        if user_pref.get("allow_public_responses"):
            return {
                "respond_publicly": True,
                "suggestion_needed": False,
                "reason": "User opted in to public responses"
            }
        
        # Check workspace policy
        if workspace_id:
            policy = self.workspace_policies.get(workspace_id, {})
            if policy.get("allow_public_responses"):
                return {
                    "respond_publicly": True,
                    "suggestion_needed": False,
                    "reason": "Workspace policy allows public responses"
                }
        
        # Check if public channel using API
        if slack_client:
            is_public = await self.is_public_channel(channel_id, slack_client)
            if is_public:
                return {
                    "respond_publicly": False,
                    "suggestion_needed": True,
                    "reason": "Public channel - suggesting DM for privacy"
                }
        
        # Default: public channels suggest DM
        if channel_id.startswith('C'):
            return {
                "respond_publicly": False,
                "suggestion_needed": True,
                "reason": "Public channel - suggesting DM"
            }
        
        # Default to allowing
        return {
            "respond_publicly": True,
            "suggestion_needed": False,
            "reason": "Default allow"
        }
    
    async def send_dm_suggestion(
        self,
        channel_id: str,
        user_id: str,
        slack_client: Any,
        bot_user_id: Optional[str] = None
    ):
        """Send ephemeral message suggesting user DM the bot.
        
        Args:
            channel_id: Channel to send ephemeral message
            user_id: User to show message to
            slack_client: Slack client
            bot_user_id: Bot's user ID for deep link
        """
        from src.integrations.slack_formatter import SlackFormatter
        
        formatter = SlackFormatter()
        blocks = formatter.format_dm_suggestion(user_id)
        
        try:
            await slack_client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="For privacy, please ask me in a DM",
                blocks=blocks
            )
            logger.info(f"Sent DM suggestion to user {user_id} in channel {channel_id}")
        except Exception as e:
            logger.error(f"Error sending ephemeral message: {e}")
    
    async def is_potentially_sensitive(self, query_text: str) -> bool:
        """Check if query might contain sensitive information.
        
        Args:
            query_text: Query to check
            
        Returns:
            True if potentially sensitive
        """
        query_lower = query_text.lower()
        
        for pattern in self._sensitive_patterns:
            if re.search(pattern, query_lower):
                logger.warning(f"Detected potentially sensitive query pattern: {pattern}")
                return True
        
        return False
    
    async def bot_is_channel_member(
        self,
        channel_id: str,
        bot_user_id: str,
        slack_client: Any
    ) -> bool:
        """Check if bot is a member of the channel.
        
        Args:
            channel_id: Channel ID
            bot_user_id: Bot's user ID
            slack_client: Slack client
            
        Returns:
            True if bot is in channel
        """
        try:
            result = await slack_client.conversations_info(channel=channel_id)
            if result.get("ok"):
                return result.get("channel", {}).get("is_member", False)
        except Exception as e:
            logger.error(f"Error checking bot membership: {e}")
        
        return False
    
    def set_user_preference(self, user_id: str, allow_public_responses: bool):
        """Set user privacy preference.
        
        Args:
            user_id: User ID
            allow_public_responses: Whether to allow public responses
        """
        self.user_preferences[user_id] = {
            "allow_public_responses": allow_public_responses
        }
        logger.info(f"Set privacy preference for user {user_id}: allow_public={allow_public_responses}")
    
    def set_workspace_policy(self, workspace_id: str, allow_public_responses: bool):
        """Set workspace-wide privacy policy.
        
        Args:
            workspace_id: Workspace ID
            allow_public_responses: Default policy
        """
        self.workspace_policies[workspace_id] = {
            "allow_public_responses": allow_public_responses
        }
        logger.info(f"Set privacy policy for workspace {workspace_id}: allow_public={allow_public_responses}")
    
    def mark_user_rate_limited(self, user_id: str):
        """Mark user as rate limited.
        
        Args:
            user_id: User ID
        """
        # Implementation would track rate limits
        logger.warning(f"User {user_id} rate limited")
    
    def is_dm_prefix(self, channel_id: str) -> bool:
        """Check if channel ID has DM prefix."""
        return channel_id.startswith('D')
    
    def is_public_prefix(self, channel_id: str) -> bool:
        """Check if channel ID has public channel prefix."""
        return channel_id.startswith('C')
    
    def is_private_prefix(self, channel_id: str) -> bool:
        """Check if channel ID has private channel prefix."""
        return channel_id.startswith('G')
    
    def redact_sensitive_content(self, text: str) -> str:
        """Redact sensitive information from text for logging.
        
        Args:
            text: Text to redact
            
        Returns:
            Redacted text
        """
        redacted = text
        
        # Redact common secret patterns
        patterns = [
            (r'password[:\s=]+\S+', 'password=[REDACTED]'),
            (r'(sk|xox[abp])-[a-zA-Z0-9-]+', '[REDACTED_TOKEN]'),
            (r'\b[A-Za-z0-9]{32,}\b', '[REDACTED_KEY]'),
        ]
        
        for pattern, replacement in patterns:
            redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
        
        return redacted


class SlackBot:
    """Slack bot for handling ContextDock queries."""
    
    def __init__(
        self,
        slack_client: Any,
        query_service: Any,
        bot_token: str,
        app_token: str
    ):
        """Initialize Slack bot.
        
        Args:
            slack_client: Slack Web API client
            query_service: Query service for RAG
            bot_token: Slack bot token
            app_token: Slack app token
        """
        self.slack_client = slack_client
        self.query_service = query_service
        self.bot_token = bot_token
        self.app_token = app_token
        self.privacy_handler = SlackPrivacyHandler()
        self._user_email_cache: Dict[str, str] = {}
    
    async def handle_message(self, event: Dict[str, Any]):
        """Handle message event.
        
        Args:
            event: Slack message event
        """
        try:
            # Ignore bot messages
            if event.get("bot_id") or event.get("bot_profile"):
                return
            
            channel_id = event.get("channel")
            user_id = event.get("user")
            text = event.get("text", "")
            thread_ts = event.get("thread_ts")
            ts = event.get("ts")
            
            if not channel_id or not user_id or not text:
                logger.warning("Malformed message event")
                return
            
            # Only respond to DMs
            if not channel_id.startswith('D'):
                return
            
            # Get user email
            user_email = await self.get_user_email(user_id)
            
            # Query the RAG system
            try:
                result = await self.query_service.query(
                    question=text,
                    user_id=user_id,
                    user_email=user_email,
                    channel_id=channel_id
                )
                
                # Format and send response
                from src.integrations.slack_formatter import SlackFormatter
                formatter = SlackFormatter()
                blocks = formatter.format_answer(result)
                
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text=result.get("answer", "")[:100],  # Fallback text
                    blocks=blocks,
                    thread_ts=thread_ts or ts
                )
                
                logger.info(f"Sent answer to user {user_id} in channel {channel_id}")
                
            except Exception as e:
                logger.error(f"Query service error: {e}")
                from src.integrations.slack_formatter import SlackFormatter
                formatter = SlackFormatter()
                blocks = formatter.format_error(str(e))
                
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text="Sorry, I encountered an error",
                    blocks=blocks,
                    thread_ts=thread_ts or ts
                )
        
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    async def handle_app_mention(self, event: Dict[str, Any]):
        """Handle app mention event (@bot).
        
        Args:
            event: Slack app mention event
        """
        try:
            channel_id = event.get("channel")
            user_id = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")
            
            # Remove @mention from text
            text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            
            # Check privacy
            decision = await self.privacy_handler.should_respond_publicly(
                channel_id, user_id, text, slack_client=self.slack_client
            )
            
            if not decision["respond_publicly"]:
                # Send ephemeral suggestion
                await self.privacy_handler.send_dm_suggestion(
                    channel_id, user_id, self.slack_client
                )
                return
            
            # Process query
            user_email = await self.get_user_email(user_id)
            
            try:
                result = await self.query_service.query(
                    question=text,
                    user_id=user_id,
                    user_email=user_email,
                    channel_id=channel_id
                )
                
                from src.integrations.slack_formatter import SlackFormatter
                formatter = SlackFormatter()
                blocks = formatter.format_answer(result)
                
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text=result.get("answer", "")[:100],
                    blocks=blocks
                )
                
            except Exception as e:
                logger.error(f"Query error: {e}")
                from src.integrations.slack_formatter import SlackFormatter
                formatter = SlackFormatter()
                blocks = formatter.format_error(str(e))
                
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    text="Error processing query",
                    blocks=blocks
                )
        
        except Exception as e:
            logger.error(f"Error handling app mention: {e}", exc_info=True)
    
    async def handle_slash_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /ask slash command.
        
        Args:
            command: Slack slash command payload
            
        Returns:
            Response dict
        """
        try:
            text = command.get("text", "").strip()
            user_id = command.get("user_id")
            channel_id = command.get("channel_id")
            
            if not text:
                from src.integrations.slack_formatter import format_help_message
                return {
                    "response_type": "ephemeral",
                    "blocks": format_help_message()
                }
            
            # Check privacy
            decision = await self.privacy_handler.should_respond_publicly(
                channel_id, user_id, text, slack_client=self.slack_client
            )
            
            if not decision["respond_publicly"]:
                # Send ephemeral suggestion
                await self.privacy_handler.send_dm_suggestion(
                    channel_id, user_id, self.slack_client
                )
                return {
                    "response_type": "ephemeral",
                    "text": "For privacy, please ask me in a DM"
                }
            
            # Process query asynchronously
            # Return immediate acknowledgment
            return {
                "response_type": "ephemeral",
                "text": "Processing your question..."
            }
        
        except Exception as e:
            logger.error(f"Error handling slash command: {e}")
            return {
                "response_type": "ephemeral",
                "text": "Error processing command"
            }
    
    async def get_user_email(self, user_id: str) -> Optional[str]:
        """Get user email from Slack API with caching.
        
        Args:
            user_id: Slack user ID
            
        Returns:
            User email or None
        """
        # Check cache
        if user_id in self._user_email_cache:
            return self._user_email_cache[user_id]
        
        try:
            result = await self.slack_client.users_info(user=user_id)
            if result.get("ok"):
                email = result.get("user", {}).get("profile", {}).get("email")
                if email:
                    self._user_email_cache[user_id] = email
                    return email
        except Exception as e:
            logger.error(f"Error fetching user email: {e}")
        
        return None
