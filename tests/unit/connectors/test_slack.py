"""Unit tests for Slack connector.

Tests core connector functionality with mocked API responses.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.slack.connector import SlackConnector
from src.connectors.sdk import OAuth2Token
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document  # noqa: F401 - needed for SQLAlchemy relationships
from src.models.sync_run import SyncRun  # noqa: F401 - needed for SQLAlchemy relationships
from src.models.workspace import Workspace


@pytest.fixture
def test_workspace(db_session) -> Workspace:
    """Create test workspace."""
    workspace = Workspace(
        name="Test Workspace",
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def slack_connector_def(db_session) -> ConnectorDefinition:
    """Create Slack connector definition."""
    conn_def = ConnectorDefinition(
        name="Slack",
        connector_type="slack",
        description="Slack workspace connector",
        config_schema={},
        oauth_scopes=["channels:read", "channels:history"],
        supports_read=True,
        supports_write=False,
    )
    db_session.add(conn_def)
    db_session.commit()
    return conn_def


@pytest.fixture
def slack_connector_instance(db_session, test_workspace, slack_connector_def) -> Connector:
    """Create Slack connector instance."""
    connector = Connector(
        connector_definition_id=slack_connector_def.id,
        workspace_id=test_workspace.id,
        name="Test Slack",
        config_json={"workspace_url": "https://test.slack.com"},
        credentials_encrypted=b"test_encrypted_token",
        sync_schedule="hourly",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    return connector


@pytest.fixture
def slack_connector(slack_connector_instance) -> SlackConnector:
    """Create SlackConnector instance."""
    connector = SlackConnector(slack_connector_instance)
    # Inject test OAuth token
    connector._oauth_token = OAuth2Token(
        access_token="xoxb-test-token",
        token_type="Bearer",
        expires_in=43200,
        refresh_token=None,
        scope="channels:read channels:history",
        expires_at=datetime.now().timestamp() + 43200,
    )
    return connector


class TestSlackConnectorInit:
    """Test SlackConnector initialization."""

    def test_connector_initializes_with_valid_instance(
        self, slack_connector_instance
    ):
        """Verify connector initializes with valid Connector instance."""
        connector = SlackConnector(slack_connector_instance)
        
        assert connector.connector == slack_connector_instance
        assert connector.BASE_URL == "https://slack.com/api"
        assert connector._users_cache == {}
        assert connector._channels_cache == {}

    def test_connector_has_required_methods(self, slack_connector):
        """Verify connector implements required ConnectorBase methods."""
        assert hasattr(slack_connector, "sync")
        assert hasattr(slack_connector, "fetch_page")
        assert hasattr(slack_connector, "extract_acl")
        assert callable(slack_connector.sync)
        assert callable(slack_connector.fetch_page)
        assert callable(slack_connector.extract_acl)


class TestSlackConnectorAuth:
    """Test Slack authentication and headers."""

    @pytest.mark.skip(reason="Credentials decryption not implemented yet")
    def test_get_headers_creates_oauth_token_from_credentials(
        self, slack_connector_instance
    ):
        """Verify headers are created from connector credentials (mocked)."""
        connector = SlackConnector(slack_connector_instance)
        
        # TODO: Implement credentials_encrypted decryption
        # Mock credentials as dict (normally would be decrypted from encrypted bytes)
        connector.connector.credentials = {
            "access_token": "xoxb-real-token",
            "token_type": "Bearer",
            "expires_in": 43200,
            "scope": "channels:read",
            "expires_at": datetime.now().timestamp() + 43200,
        }
        
        headers = connector._get_headers()
    
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer xoxb-real-token"
        assert headers["Content-Type"] == "application/json; charset=utf-8"

    def test_get_headers_reuses_existing_token(self, slack_connector):
        """Verify existing OAuth token is reused."""
        # Get headers twice
        headers1 = slack_connector._get_headers()
        headers2 = slack_connector._get_headers()
        
        # Should use same token
        assert headers1["Authorization"] == headers2["Authorization"]
        assert "xoxb-test-token" in headers1["Authorization"]


class TestSlackACLExtraction:
    """Test Slack ACL metadata extraction."""

    def test_extract_acl_for_public_channel(self, slack_connector):
        """Verify ACL extraction for public channel messages."""
        metadata = {
            "channel_id": "C12345",
            "channel_name": "general",
            "is_private": False,
            "message_ts": "1234567890.123456",
        }
        
        acl = slack_connector.extract_acl(metadata)
        
        assert acl["channel_id"] == "C12345"
        assert acl["connector_type"] == "slack"
        assert acl["channel_type"] == "public"
        assert acl["workspace_level_access"] is True

    def test_extract_acl_for_private_channel(self, slack_connector):
        """Verify ACL extraction for private channel messages."""
        metadata = {
            "channel_id": "C67890",
            "channel_name": "private-team",
            "is_private": True,
            "message_ts": "1234567890.123456",
            "member_ids": ["U123", "U456"],
        }
        
        acl = slack_connector.extract_acl(metadata)
        
        assert acl["channel_id"] == "C67890"
        assert acl["channel_type"] == "private"
        assert acl["allowed_users"] == ["U123", "U456"]
        assert "workspace_level_access" not in acl

    def test_extract_acl_for_dm(self, slack_connector):
        """Verify ACL extraction for direct messages."""
        metadata = {
            "channel_id": "D12345",
            "is_private": True,
            "is_im": True,
            "message_ts": "1234567890.123456",
            "participants": ["U123", "U456"],
        }
        
        acl = slack_connector.extract_acl(metadata)
        
        assert acl["channel_type"] == "dm"
        assert acl["allowed_users"] == ["U123", "U456"]


class TestSlackAPIFetching:
    """Test Slack API fetch methods with mocked responses."""

    @patch("src.connectors.slack.connector.requests.get")
    def test_fetch_channels_page_success(
        self, mock_get, slack_connector
    ):
        """Verify _fetch_channels_page handles successful response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channels": [
                {"id": "C123", "name": "general", "is_private": False},
                {"id": "C456", "name": "random", "is_private": False},
            ],
            "response_metadata": {"next_cursor": "cursor123"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = slack_connector._fetch_channels_page(limit=10)
        
        assert result["ok"] is True
        assert len(result["channels"]) == 2
        assert result["response_metadata"]["next_cursor"] == "cursor123"
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "conversations.list" in call_args[0][0]

    @patch("src.connectors.slack.connector.requests.get")
    def test_fetch_channels_page_handles_error(
        self, mock_get, slack_connector
    ):
        """Verify _fetch_channels_page handles API errors."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "invalid_auth",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            slack_connector._fetch_channels_page()
        
        assert "invalid_auth" in str(exc_info.value)

    @patch("src.connectors.slack.connector.requests.get")
    def test_fetch_messages_page_with_cursor(
        self, mock_get, slack_connector
    ):
        """Verify _fetch_messages_page uses cursor and oldest parameters."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "messages": [
                {"ts": "1234.5678", "text": "Hello", "user": "U123"},
            ],
            "has_more": True,
            "response_metadata": {"next_cursor": "cursor456"},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = slack_connector._fetch_messages_page(
            "C123", cursor="cursor123", oldest="1234567890"
        )
        
        assert result["ok"] is True
        assert len(result["messages"]) == 1
        
        # Verify cursor and oldest were passed
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert params["cursor"] == "cursor123"
        assert params["oldest"] == "1234567890"

    @patch("src.connectors.slack.connector.requests.get")
    def test_fetch_users_page_success(self, mock_get, slack_connector):
        """Verify _fetch_users_page fetches user list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "members": [
                {
                    "id": "U123",
                    "real_name": "John Doe",
                    "deleted": False,
                    "is_bot": False,
                    "profile": {"email": "john@example.com"},
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = slack_connector._fetch_users_page()
        
        assert result["ok"] is True
        assert len(result["members"]) == 1
        assert result["members"][0]["id"] == "U123"


class TestSlackSync:
    """Test Slack sync functionality."""

    @patch.object(SlackConnector, "_load_users_cache")
    @patch.object(SlackConnector, "_load_channels_cache")
    @patch.object(SlackConnector, "_fetch_channels_page")
    @patch.object(SlackConnector, "_fetch_messages_page")
    def test_sync_yields_documents(
        self,
        mock_fetch_messages,
        mock_fetch_channels,
        mock_load_channels_cache,
        mock_load_users_cache,
        slack_connector,
    ):
        """Verify sync() yields documents with proper structure."""
        # Mock channels response
        mock_fetch_channels.return_value = {
            "ok": True,
            "channels": [
                {
                    "id": "C123",
                    "name": "general",
                    "is_private": False,
                    "is_member": True,
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }
        
        # Mock messages response
        mock_fetch_messages.return_value = {
            "ok": True,
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Hello world",
                    "user": "U123",
                    "type": "message",
                    "reply_count": 0,
                },
            ],
            "has_more": False,
            "response_metadata": {"next_cursor": ""},
        }
        
        # Mock user cache
        slack_connector._users_cache = {
            "U123": {
                "id": "U123",
                "real_name": "John Doe",
                "profile": {"email": "john@example.com"},
            }
        }
        
        # Run sync
        documents = list(slack_connector.sync(max_channels=1, max_messages_per_channel=1))
        
        assert len(documents) == 1
        doc = documents[0]
        
        # Verify document structure
        assert doc["source_id"] == "slack_C123_1234567890.123456"
        assert doc["source_type"] == "slack"
        assert doc["content"] == "Hello world"
        assert doc["metadata"]["channel_id"] == "C123"
        assert doc["metadata"]["channel_name"] == "general"
        assert doc["metadata"]["user_email"] == "john@example.com"
        assert "acl_metadata" in doc

    @patch.object(SlackConnector, "_load_users_cache")
    @patch.object(SlackConnector, "_load_channels_cache")
    @patch.object(SlackConnector, "_fetch_channels_page")
    def test_sync_skips_non_member_channels(
        self,
        mock_fetch_channels,
        mock_load_channels_cache,
        mock_load_users_cache,
        slack_connector,
    ):
        """Verify sync() skips channels where bot is not a member."""
        mock_fetch_channels.return_value = {
            "ok": True,
            "channels": [
                {
                    "id": "C123",
                    "name": "private-team",
                    "is_private": True,
                    "is_member": False,  # Not a member
                },
            ],
            "response_metadata": {"next_cursor": ""},
        }
        
        documents = list(slack_connector.sync(max_channels=1))
        
        # Should yield no documents
        assert len(documents) == 0

    @patch.object(SlackConnector, "_load_users_cache")
    @patch.object(SlackConnector, "_load_channels_cache")
    @patch.object(SlackConnector, "_fetch_channels_page")
    @patch.object(SlackConnector, "_fetch_messages_page")
    def test_sync_respects_max_channels_limit(
        self,
        mock_fetch_messages,
        mock_fetch_channels,
        mock_load_channels_cache,
        mock_load_users_cache,
        slack_connector,
    ):
        """Verify sync() respects max_channels parameter."""
        # Return 3 channels
        mock_fetch_channels.return_value = {
            "ok": True,
            "channels": [
                {"id": f"C{i}", "name": f"channel-{i}", "is_private": False, "is_member": True}
                for i in range(3)
            ],
            "response_metadata": {"next_cursor": ""},
        }
        
        mock_fetch_messages.return_value = {
            "ok": True,
            "messages": [
                {"ts": "1234.5678", "text": "Test", "user": "U123", "reply_count": 0}
            ],
            "has_more": False,
            "response_metadata": {"next_cursor": ""},
        }
        
        # Sync with max_channels=2
        documents = list(slack_connector.sync(max_channels=2, max_messages_per_channel=1))
        
        # Should only process 2 channels = 2 documents
        assert len(documents) == 2
