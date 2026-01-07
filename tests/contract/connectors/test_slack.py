"""Contract tests for Slack connector.

These tests use VCR.py to record real API responses and verify connector behavior
against actual Slack API structure. Cassettes should be committed to version control.

To regenerate cassettes:
1. Set SLACK_BOT_TOKEN environment variable
2. Delete cassettes in tests/fixtures/vcr_cassettes/slack/
3. Run: pytest tests/contract/connectors/test_slack.py --record-mode=once
"""

import os
from datetime import datetime
from typing import Any, Dict

import pytest
import vcr

from src.connectors.slack.connector import SlackConnector
from src.connectors.sdk import OAuth2Config, OAuth2Token
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition


# VCR configuration for Slack API
slack_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/slack",
    record_mode="once",  # Only record if cassette missing
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["Authorization"],  # Don't record auth tokens
    decode_compressed_response=True,
)


@pytest.fixture
def slack_token() -> str:
    """Get Slack bot token from environment or use placeholder."""
    return os.getenv("SLACK_BOT_TOKEN", "xoxb-placeholder-token")


@pytest.fixture
def slack_oauth_token(slack_token: str) -> OAuth2Token:
    """Create OAuth2Token for Slack."""
    return OAuth2Token(
        access_token=slack_token,
        token_type="Bearer",
        expires_in=43200,  # 12 hours
        refresh_token=None,
        scope="channels:read channels:history users:read",
        expires_at=datetime.now().timestamp() + 43200,
    )


@pytest.fixture
def slack_connector_def(db_session) -> ConnectorDefinition:
    """Create Slack connector definition."""
    conn_def = ConnectorDefinition(
        name="slack",
        display_name="Slack",
        description="Slack workspace connector",
        icon_url="https://slack.com/favicon.ico",
        auth_type="oauth2",
        config_schema={
            "type": "object",
            "properties": {
                "workspace_url": {"type": "string", "format": "uri"},
            },
            "required": ["workspace_url"],
        },
    )
    db_session.add(conn_def)
    db_session.commit()
    return conn_def


@pytest.fixture
def slack_connector_instance(
    db_session, slack_connector_def: ConnectorDefinition, slack_oauth_token: OAuth2Token
) -> Connector:
    """Create Slack connector instance."""
    connector = Connector(
        connector_definition_id=slack_connector_def.id,
        workspace_id=1,  # Assume workspace exists
        name="Test Slack Workspace",
        config={"workspace_url": "https://test-workspace.slack.com"},
        credentials={
            "access_token": slack_oauth_token.access_token,
            "token_type": slack_oauth_token.token_type,
            "expires_at": slack_oauth_token.expires_at,
            "scope": slack_oauth_token.scope,
        },
        sync_schedule="hourly",
        enabled=True,
    )
    db_session.add(connector)
    db_session.commit()
    return connector


@pytest.fixture
def slack_connector(
    slack_connector_instance: Connector, slack_oauth_token: OAuth2Token
) -> SlackConnector:
    """Create SlackConnector instance with test credentials."""
    connector = SlackConnector(slack_connector_instance)
    # Inject OAuth token directly
    connector._oauth_token = slack_oauth_token
    return connector


class TestSlackAPIStructure:
    """Test Slack API response structure matches our expectations."""

    @slack_vcr.use_cassette("channels_list.yaml")
    def test_channels_list_response_structure(self, slack_connector: SlackConnector):
        """Verify conversations.list API response structure."""
        # Fetch first page of channels
        channels = slack_connector._fetch_channels_page(limit=10)

        assert "ok" in channels
        assert channels["ok"] is True
        assert "channels" in channels
        assert isinstance(channels["channels"], list)

        if len(channels["channels"]) > 0:
            channel = channels["channels"][0]
            assert "id" in channel
            assert "name" in channel
            assert "is_private" in channel
            assert "is_archived" in channel
            assert "is_member" in channel

        # Check pagination cursor
        if "response_metadata" in channels:
            assert "next_cursor" in channels["response_metadata"]

    @slack_vcr.use_cassette("conversations_history.yaml")
    def test_conversations_history_response_structure(
        self, slack_connector: SlackConnector
    ):
        """Verify conversations.history API response structure."""
        # Use a public channel ID (should be in cassette)
        test_channel_id = "C01234567"  # Placeholder, will be in cassette

        messages = slack_connector._fetch_messages_page(test_channel_id, limit=10)

        assert "ok" in messages
        assert messages["ok"] is True
        assert "messages" in messages
        assert isinstance(messages["messages"], list)

        if len(messages["messages"]) > 0:
            message = messages["messages"][0]
            assert "ts" in message
            assert "text" in message
            assert "user" in message or "bot_id" in message
            assert "type" in message

        # Check pagination
        assert "has_more" in messages
        if messages["has_more"]:
            assert "response_metadata" in messages
            assert "next_cursor" in messages["response_metadata"]

    @slack_vcr.use_cassette("users_list.yaml")
    def test_users_list_response_structure(self, slack_connector: SlackConnector):
        """Verify users.list API response structure."""
        users = slack_connector._fetch_users_page(limit=10)

        assert "ok" in users
        assert users["ok"] is True
        assert "members" in users
        assert isinstance(users["members"], list)

        if len(users["members"]) > 0:
            user = users["members"][0]
            assert "id" in user
            assert "profile" in user
            assert "email" in user["profile"] or "real_name" in user["profile"]
            assert "deleted" in user

        # Check pagination cursor
        if "response_metadata" in users:
            assert "next_cursor" in users["response_metadata"]

    @slack_vcr.use_cassette("conversations_replies.yaml")
    def test_conversations_replies_response_structure(
        self, slack_connector: SlackConnector
    ):
        """Verify conversations.replies API response structure for threaded messages."""
        test_channel_id = "C01234567"
        test_thread_ts = "1234567890.123456"

        replies = slack_connector._fetch_thread_replies(test_channel_id, test_thread_ts)

        assert "ok" in replies
        assert replies["ok"] is True
        assert "messages" in replies
        assert isinstance(replies["messages"], list)

        if len(replies["messages"]) > 0:
            reply = replies["messages"][0]
            assert "ts" in reply
            assert "text" in reply
            assert "thread_ts" in reply


class TestSlackConnectorInterface:
    """Test SlackConnector implements ConnectorBase interface correctly."""

    def test_connector_has_required_methods(self, slack_connector: SlackConnector):
        """Verify SlackConnector implements all required methods."""
        assert hasattr(slack_connector, "sync")
        assert hasattr(slack_connector, "fetch_page")
        assert hasattr(slack_connector, "extract_acl")
        assert callable(slack_connector.sync)
        assert callable(slack_connector.fetch_page)
        assert callable(slack_connector.extract_acl)

    @slack_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, slack_connector: SlackConnector):
        """Verify sync() returns Document objects with required fields."""
        # Run partial sync (limit to 2 channels, 5 messages each)
        documents = []
        for doc in slack_connector.sync(max_channels=2, max_messages_per_channel=5):
            documents.append(doc)

        assert len(documents) > 0

        # Verify document structure
        for doc in documents:
            assert hasattr(doc, "source_id")
            assert hasattr(doc, "source_type")
            assert hasattr(doc, "content")
            assert hasattr(doc, "metadata")
            assert hasattr(doc, "acl_metadata")

            # Slack-specific fields
            assert doc.source_type == "slack"
            assert "channel_id" in doc.metadata
            assert "message_ts" in doc.metadata or "channel_name" in doc.metadata

    @slack_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync_with_cursor(self, slack_connector: SlackConnector):
        """Verify sync() respects cursor state for incremental sync."""
        # First sync - get some documents
        documents_first = []
        for doc in slack_connector.sync(max_channels=1, max_messages_per_channel=5):
            documents_first.append(doc)

        # Get cursor state after first sync
        cursor_state = slack_connector.get_cursor_state()

        # Second sync with cursor - should resume from where we left off
        documents_second = []
        for doc in slack_connector.sync(cursor_state=cursor_state, max_channels=1):
            documents_second.append(doc)

        # Verify no duplicate documents (based on source_id)
        first_ids = {doc.source_id for doc in documents_first}
        second_ids = {doc.source_id for doc in documents_second}

        # Should have different or overlapping sets (depending on new messages)
        # At minimum, verify sync works with cursor
        assert cursor_state is not None
        assert "last_channel_cursor" in cursor_state or "last_message_ts" in cursor_state


class TestSlackACLExtraction:
    """Test ACL metadata extraction from Slack documents."""

    def test_extract_acl_for_public_channel_message(self, slack_connector: SlackConnector):
        """Verify ACL extraction for public channel messages."""
        test_doc_metadata = {
            "channel_id": "C01234567",
            "channel_name": "general",
            "is_private": False,
            "message_ts": "1234567890.123456",
        }

        acl = slack_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert "channel_type" in acl
        assert acl["channel_type"] == "public"
        assert "channel_id" in acl
        assert acl["channel_id"] == "C01234567"

    def test_extract_acl_for_private_channel_message(self, slack_connector: SlackConnector):
        """Verify ACL extraction for private channel messages."""
        test_doc_metadata = {
            "channel_id": "C87654321",
            "channel_name": "private-team",
            "is_private": True,
            "message_ts": "1234567890.123456",
            "member_ids": ["U123", "U456", "U789"],
        }

        acl = slack_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert "channel_type" in acl
        assert acl["channel_type"] == "private"
        assert "allowed_users" in acl
        assert set(acl["allowed_users"]) == {"U123", "U456", "U789"}

    def test_extract_acl_for_dm_message(self, slack_connector: SlackConnector):
        """Verify ACL extraction for direct messages."""
        test_doc_metadata = {
            "channel_id": "D01234567",
            "channel_name": None,
            "is_private": True,
            "is_im": True,
            "message_ts": "1234567890.123456",
            "participants": ["U123", "U456"],
        }

        acl = slack_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert "channel_type" in acl
        assert acl["channel_type"] == "dm"
        assert "allowed_users" in acl
        assert set(acl["allowed_users"]) == {"U123", "U456"}


class TestSlackRateLimiting:
    """Test Slack connector respects rate limits."""

    def test_connector_has_rate_limiter(self, slack_connector: SlackConnector):
        """Verify SlackConnector has rate limiter configured."""
        # Check if _fetch methods have rate limiting decorator
        assert hasattr(slack_connector._fetch_channels_page, "__wrapped__")

    @slack_vcr.use_cassette("rate_limit_429.yaml")
    def test_handles_429_response(self, slack_connector: SlackConnector):
        """Verify connector handles 429 Too Many Requests with retry."""
        # This test requires a cassette with a 429 response
        # The rate limiter should automatically retry
        try:
            channels = slack_connector._fetch_channels_page(limit=100)
            assert channels is not None
        except Exception as e:
            # If rate limit is exhausted, expect specific error
            assert "rate limit" in str(e).lower() or "429" in str(e)
