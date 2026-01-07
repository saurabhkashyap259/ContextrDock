"""Contract tests for Confluence connector.

These tests use VCR.py to record real API responses and verify connector behavior
against actual Confluence Cloud API structure.
"""

import os
from datetime import datetime

import pytest
import vcr

from src.connectors.confluence.connector import ConfluenceConnector
from src.connectors.sdk import OAuth2Token
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document  # noqa: F401
from src.models.sync_run import SyncRun  # noqa: F401
from src.models.workspace import Workspace


# VCR configuration for Confluence API
confluence_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/confluence",
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["Authorization"],
    decode_compressed_response=True,
)


@pytest.fixture
def confluence_token() -> str:
    """Get Confluence OAuth token from environment or use placeholder."""
    return os.getenv("CONFLUENCE_ACCESS_TOKEN", "placeholder-token")


@pytest.fixture
def confluence_oauth_token(confluence_token: str) -> OAuth2Token:
    """Create OAuth2Token for Confluence."""
    return OAuth2Token(
        access_token=confluence_token,
        token_type="Bearer",
        expires_in=3600,
        refresh_token=None,
        scope="read:confluence-content.all",
        expires_at=datetime.now().timestamp() + 3600,
    )


@pytest.fixture
def confluence_connector_def(db_session) -> ConnectorDefinition:
    """Create Confluence connector definition."""
    conn_def = ConnectorDefinition(
        name="Confluence",
        connector_type="confluence",
        description="Confluence Cloud connector",
        config_schema={},
        oauth_scopes=["read:confluence-content.all"],
        supports_read=True,
        supports_write=False,
    )
    db_session.add(conn_def)
    db_session.commit()
    return conn_def


@pytest.fixture
def confluence_connector_instance(
    db_session, confluence_connector_def: ConnectorDefinition, confluence_oauth_token: OAuth2Token
) -> Connector:
    """Create Confluence connector instance."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    connector = Connector(
        connector_definition_id=confluence_connector_def.id,
        workspace_id=workspace.id,
        name="Test Confluence",
        config_json={"instance_url": "https://test-company.atlassian.net"},
        credentials_encrypted=b"test_encrypted_token",
        sync_schedule="6-hourly",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    return connector


@pytest.fixture
def confluence_connector(
    confluence_connector_instance: Connector, confluence_oauth_token: OAuth2Token
) -> ConfluenceConnector:
    """Create ConfluenceConnector instance with test credentials."""
    connector = ConfluenceConnector(confluence_connector_instance)
    connector._oauth_token = confluence_oauth_token
    return connector


class TestConfluenceAPIStructure:
    """Test Confluence API response structure matches our expectations."""

    @confluence_vcr.use_cassette("spaces_list.yaml")
    def test_spaces_list_response_structure(self, confluence_connector: ConfluenceConnector):
        """Verify /space API response structure."""
        result = confluence_connector._fetch_spaces_page(limit=10)

        assert "results" in result
        assert "size" in result
        assert "start" in result

        if len(result["results"]) > 0:
            space = result["results"][0]
            assert "key" in space
            assert "name" in space
            assert "type" in space

    @confluence_vcr.use_cassette("content_search.yaml")
    def test_content_search_response_structure(self, confluence_connector: ConfluenceConnector):
        """Verify /content API response structure."""
        result = confluence_connector._fetch_pages_page(limit=10)

        assert "results" in result
        assert "size" in result

        if len(result["results"]) > 0:
            page = result["results"][0]
            assert "id" in page
            assert "title" in page
            assert "type" in page
            assert "space" in page

    @confluence_vcr.use_cassette("page_restrictions.yaml")
    def test_page_restrictions_response_structure(
        self, confluence_connector: ConfluenceConnector
    ):
        """Verify /content/{id}/restriction API response structure."""
        # Use a test page ID (should be in cassette)
        test_page_id = "123456"

        result = confluence_connector._fetch_page_restrictions(test_page_id)

        assert "read" in result or "update" in result


class TestConfluenceConnectorInterface:
    """Test ConfluenceConnector implements ConnectorBase interface correctly."""

    def test_connector_has_required_methods(self, confluence_connector: ConfluenceConnector):
        """Verify ConfluenceConnector implements all required methods."""
        assert hasattr(confluence_connector, "sync")
        assert hasattr(confluence_connector, "fetch_page")
        assert hasattr(confluence_connector, "extract_acl")
        assert callable(confluence_connector.sync)
        assert callable(confluence_connector.fetch_page)
        assert callable(confluence_connector.extract_acl)

    @confluence_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, confluence_connector: ConfluenceConnector):
        """Verify sync() returns Document objects with required fields."""
        documents = []
        for doc in confluence_connector.sync(max_pages=2):
            documents.append(doc)

        assert len(documents) > 0

        # Verify document structure
        for doc in documents:
            assert "source_id" in doc
            assert "source_type" in doc
            assert "content" in doc
            assert "metadata" in doc
            assert "acl_metadata" in doc

            # Confluence-specific fields
            assert doc["source_type"] == "confluence"
            assert "page_id" in doc["metadata"]
            assert "space_key" in doc["metadata"]

    @confluence_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync_with_timestamp(self, confluence_connector: ConfluenceConnector):
        """Verify sync() supports incremental sync."""
        # First sync
        documents_first = []
        for doc in confluence_connector.sync(max_pages=2):
            documents_first.append(doc)

        # Get cursor state
        cursor_state = confluence_connector.get_cursor_state()

        # Second sync with cursor
        documents_second = []
        for doc in confluence_connector.sync(cursor_state=cursor_state, max_pages=2):
            documents_second.append(doc)

        # Verify cursor state contains timestamp
        assert cursor_state is not None
        assert "last_sync_timestamp" in cursor_state


class TestConfluenceACLExtraction:
    """Test ACL metadata extraction from Confluence documents."""

    def test_extract_acl_for_space_level_page(self, confluence_connector: ConfluenceConnector):
        """Verify ACL extraction for pages without restrictions."""
        test_doc_metadata = {
            "page_id": "123456",
            "page_title": "Test Page",
            "space_key": "ENG",
            "space_name": "Engineering",
        }

        acl = confluence_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert acl["connector_type"] == "confluence"
        assert acl["space_key"] == "ENG"
        assert acl["access_level"] == "space"
        assert acl["requires_space_permission"] is True

    def test_extract_acl_for_restricted_page(self, confluence_connector: ConfluenceConnector):
        """Verify ACL extraction for pages with restrictions."""
        test_doc_metadata = {
            "page_id": "789012",
            "page_title": "Confidential Page",
            "space_key": "ENG",
            "space_name": "Engineering",
            "restricted_users": ["user-123", "user-456"],
            "restricted_groups": ["admin-group"],
        }

        acl = confluence_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert acl["access_level"] == "restricted"
        assert acl["allowed_users"] == ["user-123", "user-456"]
        assert acl["allowed_groups"] == ["admin-group"]


class TestConfluenceRateLimiting:
    """Test Confluence connector respects rate limits."""

    def test_connector_has_rate_limiter(self, confluence_connector: ConfluenceConnector):
        """Verify ConfluenceConnector has rate limiter configured."""
        # Check if _fetch methods have rate limiting decorator
        assert hasattr(confluence_connector._fetch_spaces_page, "__wrapped__")
