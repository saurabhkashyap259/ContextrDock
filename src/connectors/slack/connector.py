"""Slack connector implementation.

Fetches channels, messages (with threads), and user information from Slack workspaces.
Supports incremental sync using cursor-based pagination and message timestamps.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Optional

import requests

from src.connectors.sdk import (
    ConnectorBase,
    CursorPaginator,
    OAuth2Token,
    PageResult,
    rate_limit,
)
from src.models.connector import Connector

logger = logging.getLogger(__name__)


class SlackConnector(ConnectorBase):
    """Slack workspace connector.

    Fetches:
    - Public and private channels the bot is a member of
    - Messages and threaded replies from channels
    - User information for identity resolution

    OAuth Scopes Required:
    - channels:read - List public channels
    - channels:history - Read public channel messages
    - groups:read - List private channels
    - groups:history - Read private channel messages
    - users:read - List workspace users
    - users:read.email - Access user email addresses
    """

    BASE_URL = "https://slack.com/api"
    RATE_LIMIT_CALLS = 50  # Tier 3 methods allow 50+ calls per minute
    RATE_LIMIT_PERIOD = 60  # seconds

    def __init__(self, connector: Connector):
        """Initialize Slack connector.

        Args:
            connector: Connector model instance with credentials
        """
        super().__init__(connector)
        self._oauth_token: Optional[OAuth2Token] = None
        self._users_cache: dict[str, dict[str, Any]] = {}
        self._channels_cache: dict[str, dict[str, Any]] = {}

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with authorization."""
        if self._oauth_token is None:
            # Load token from connector credentials
            creds = self.connector.credentials
            self._oauth_token = OAuth2Token(
                access_token=creds["access_token"],
                token_type=creds.get("token_type", "Bearer"),
                expires_in=creds.get("expires_in", 43200),
                refresh_token=creds.get("refresh_token"),
                scope=creds.get("scope", ""),
                expires_at=creds.get("expires_at", datetime.now().timestamp() + 43200),
            )

        return {
            "Authorization": f"Bearer {self._oauth_token.access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_channels_page(
        self, cursor: Optional[str] = None, limit: int = 200
    ) -> dict[str, Any]:
        """Fetch page of channels from Slack API.

        Args:
            cursor: Pagination cursor from previous response
            limit: Number of channels per page (max 200)

        Returns:
            API response with channels list and next_cursor
        """
        url = f"{self.BASE_URL}/conversations.list"
        params = {
            "limit": limit,
            "exclude_archived": True,
            "types": "public_channel,private_channel",
        }
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise Exception(f"Slack API error: {error}")

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_messages_page(
        self,
        channel_id: str,
        cursor: Optional[str] = None,
        oldest: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Fetch page of messages from a Slack channel.

        Args:
            channel_id: Slack channel ID
            cursor: Pagination cursor from previous response
            oldest: Fetch messages after this timestamp (for incremental sync)
            limit: Number of messages per page (max 1000)

        Returns:
            API response with messages list and pagination info
        """
        url = f"{self.BASE_URL}/conversations.history"
        params = {
            "channel": channel_id,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        if oldest:
            params["oldest"] = oldest

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise Exception(f"Slack API error: {error}")

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_thread_replies(
        self, channel_id: str, thread_ts: str
    ) -> dict[str, Any]:
        """Fetch replies to a threaded message.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp (parent message timestamp)

        Returns:
            API response with thread replies
        """
        url = f"{self.BASE_URL}/conversations.replies"
        params = {
            "channel": channel_id,
            "ts": thread_ts,
        }

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise Exception(f"Slack API error: {error}")

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_users_page(
        self, cursor: Optional[str] = None, limit: int = 200
    ) -> dict[str, Any]:
        """Fetch page of users from Slack API.

        Args:
            cursor: Pagination cursor from previous response
            limit: Number of users per page (max 200)

        Returns:
            API response with users list and next_cursor
        """
        url = f"{self.BASE_URL}/users.list"
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise Exception(f"Slack API error: {error}")

        return data

    def _load_users_cache(self) -> None:
        """Load all users into cache for identity resolution."""
        logger.info("Loading Slack users into cache")

        def fetch_users_page(cursor: Optional[str] = None) -> PageResult:
            data = self._fetch_users_page(cursor=cursor)
            users = data.get("members", [])
            next_cursor = data.get("response_metadata", {}).get("next_cursor")
            has_more = bool(next_cursor)
            return PageResult(items=users, next_cursor=next_cursor, has_more=has_more)

        paginator = CursorPaginator(fetch_users_page)
        for user in paginator:
            if not user.get("deleted") and not user.get("is_bot"):
                self._users_cache[user["id"]] = user

        logger.info(f"Loaded {len(self._users_cache)} users into cache")

    def _load_channels_cache(self) -> None:
        """Load all channels into cache for metadata enrichment."""
        logger.info("Loading Slack channels into cache")

        def fetch_channels_page(cursor: Optional[str] = None) -> PageResult:
            data = self._fetch_channels_page(cursor=cursor)
            channels = data.get("channels", [])
            next_cursor = data.get("response_metadata", {}).get("next_cursor")
            has_more = bool(next_cursor)
            return PageResult(items=channels, next_cursor=next_cursor, has_more=has_more)

        paginator = CursorPaginator(fetch_channels_page)
        for channel in paginator:
            self._channels_cache[channel["id"]] = channel

        logger.info(f"Loaded {len(self._channels_cache)} channels into cache")

    def sync(
        self,
        cursor_state: Optional[dict[str, Any]] = None,
        max_channels: Optional[int] = None,
        max_messages_per_channel: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Sync messages from Slack workspace.

        Args:
            cursor_state: State from previous sync for incremental updates
            max_channels: Limit number of channels to sync (for testing)
            max_messages_per_channel: Limit messages per channel (for testing)

        Yields:
            Document dicts with content, metadata, and acl_metadata
        """
        logger.info(f"Starting Slack sync for connector {self.connector.id}")

        # Load users and channels into cache
        self._load_users_cache()
        self._load_channels_cache()

        # Get cursor state
        last_channel_cursor = None
        last_sync_timestamp = None
        if cursor_state:
            last_channel_cursor = cursor_state.get("last_channel_cursor")
            last_sync_timestamp = cursor_state.get("last_sync_timestamp")

        # Fetch channels
        def fetch_channels_page(cursor: Optional[str] = None) -> PageResult:
            data = self._fetch_channels_page(cursor=cursor)
            channels = data.get("channels", [])
            next_cursor = data.get("response_metadata", {}).get("next_cursor")
            has_more = bool(next_cursor)
            return PageResult(items=channels, next_cursor=next_cursor, has_more=has_more)

        channels_paginator = CursorPaginator(
            fetch_channels_page, initial_cursor=last_channel_cursor
        )
        channels_processed = 0

        for channel in channels_paginator:
            if max_channels and channels_processed >= max_channels:
                break

            channel_id = channel["id"]
            channel_name = channel["name"]
            is_private = channel.get("is_private", False)
            is_member = channel.get("is_member", False)

            # Skip channels we're not a member of
            if not is_member:
                logger.debug(f"Skipping channel {channel_name} (not a member)")
                continue

            logger.info(
                f"Syncing channel: {channel_name} ({'private' if is_private else 'public'})"
            )

            # Fetch messages from channel
            def fetch_messages_page(cursor: Optional[str] = None) -> PageResult:
                # Use oldest timestamp for incremental sync
                oldest = last_sync_timestamp if cursor is None else None
                data = self._fetch_messages_page(
                    channel_id, cursor=cursor, oldest=oldest
                )
                messages = data.get("messages", [])
                next_cursor = data.get("response_metadata", {}).get("next_cursor")
                has_more = bool(next_cursor)
                return PageResult(items=messages, next_cursor=next_cursor, has_more=has_more)

            messages_paginator = CursorPaginator(fetch_messages_page)
            messages_processed = 0

            for message in messages_paginator:
                if max_messages_per_channel and messages_processed >= max_messages_per_channel:
                    break

                # Extract message details
                message_ts = message.get("ts")
                message_text = message.get("text", "")
                user_id = message.get("user")
                thread_ts = message.get("thread_ts")
                reply_count = message.get("reply_count", 0)

                # Skip empty messages
                if not message_text:
                    continue

                # Build document metadata
                metadata = {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "is_private": is_private,
                    "message_ts": message_ts,
                    "user_id": user_id,
                    "has_thread": reply_count > 0,
                    "source_url": f"https://{self.connector.config.get('workspace_url', 'workspace')}.slack.com/archives/{channel_id}/p{message_ts.replace('.', '')}",
                }

                # Get user info from cache
                if user_id and user_id in self._users_cache:
                    user = self._users_cache[user_id]
                    metadata["user_name"] = user.get("real_name") or user.get("name")
                    metadata["user_email"] = user.get("profile", {}).get("email")

                # Extract ACL metadata
                acl_metadata = self.extract_acl(metadata)

                # Yield message document
                document = {
                    "source_id": f"slack_{channel_id}_{message_ts}",
                    "source_type": "slack",
                    "content": message_text,
                    "metadata": metadata,
                    "acl_metadata": acl_metadata,
                }
                yield document

                # Fetch thread replies if exists
                if reply_count > 0 and thread_ts:
                    try:
                        replies_data = self._fetch_thread_replies(channel_id, thread_ts)
                        replies = replies_data.get("messages", [])

                        # Skip first message (parent message already processed)
                        for reply in replies[1:]:
                            reply_ts = reply.get("ts")
                            reply_text = reply.get("text", "")
                            reply_user_id = reply.get("user")

                            if not reply_text:
                                continue

                            reply_metadata = {
                                "channel_id": channel_id,
                                "channel_name": channel_name,
                                "is_private": is_private,
                                "message_ts": reply_ts,
                                "thread_ts": thread_ts,
                                "user_id": reply_user_id,
                                "is_thread_reply": True,
                                "source_url": f"https://{self.connector.config.get('workspace_url', 'workspace')}.slack.com/archives/{channel_id}/p{thread_ts.replace('.', '')}?thread_ts={thread_ts}&cid={channel_id}",
                            }

                            if reply_user_id and reply_user_id in self._users_cache:
                                user = self._users_cache[reply_user_id]
                                reply_metadata["user_name"] = user.get("real_name") or user.get("name")
                                reply_metadata["user_email"] = user.get("profile", {}).get("email")

                            reply_acl = self.extract_acl(reply_metadata)

                            reply_document = {
                                "source_id": f"slack_{channel_id}_{reply_ts}",
                                "source_type": "slack",
                                "content": reply_text,
                                "metadata": reply_metadata,
                                "acl_metadata": reply_acl,
                            }
                            yield reply_document

                    except Exception as e:
                        logger.warning(f"Failed to fetch thread replies for {thread_ts}: {e}")

                messages_processed += 1

            channels_processed += 1

            # Update cursor state after each channel
            self._cursor_state = {
                "last_channel_cursor": channels_paginator.current_cursor,
                "last_sync_timestamp": datetime.now().isoformat(),
            }

        logger.info(
            f"Slack sync complete: {channels_processed} channels, yielded documents"
        )

    def fetch_page(
        self, page_cursor: Optional[str] = None, page_size: int = 100
    ) -> dict[str, Any]:
        """Fetch a page of channels (for API compatibility).

        Args:
            page_cursor: Pagination cursor
            page_size: Number of items per page

        Returns:
            Page of channels with cursor
        """
        data = self._fetch_channels_page(cursor=page_cursor, limit=page_size)
        return {
            "items": data.get("channels", []),
            "next_cursor": data.get("response_metadata", {}).get("next_cursor"),
            "has_more": bool(data.get("response_metadata", {}).get("next_cursor")),
        }

    def extract_acl(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Extract ACL metadata from document metadata.

        Args:
            metadata: Document metadata with channel info

        Returns:
            ACL metadata with access control rules
        """
        channel_id = metadata.get("channel_id")
        is_private = metadata.get("is_private", False)
        is_im = metadata.get("is_im", False)

        acl = {
            "channel_id": channel_id,
            "connector_type": "slack",
        }

        if is_im:
            # Direct message - only participants
            acl["channel_type"] = "dm"
            acl["allowed_users"] = metadata.get("participants", [])
        elif is_private:
            # Private channel - only members
            acl["channel_type"] = "private"
            # Get member list from channel cache
            if channel_id in self._channels_cache:
                channel = self._channels_cache[channel_id]
                # Note: For full ACL, would need to fetch channel members separately
                # For MVP, we'll use a placeholder that needs to be populated
                acl["allowed_users"] = metadata.get("member_ids", [])
            else:
                acl["allowed_users"] = []
        else:
            # Public channel - all workspace members
            acl["channel_type"] = "public"
            acl["workspace_level_access"] = True

        return acl
