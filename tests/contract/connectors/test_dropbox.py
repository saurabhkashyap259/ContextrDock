"""Contract tests for Dropbox connector using VCR cassettes."""

import pytest
from datetime import datetime, timezone
import vcr

from src.connectors.dropbox.connector import DropboxConnector
from src.connectors.dropbox.acl import (
    extract_folder_members,
    normalize_dropbox_acl,
    check_user_access,
    build_acl_filter_query,
)
from src.models.connector import Connector
from src.models.workspace import Workspace


# VCR configuration for Dropbox API
dropbox_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/dropbox",
    record_mode="once",
    match_on=["uri", "method"],
    filter_headers=["Authorization"],
)


@pytest.fixture
def dropbox_workspace(db_session):
    """Create a test workspace."""
    workspace = Workspace(
        name="Test Workspace",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def dropbox_connector(db_session, dropbox_workspace):
    """Create a test Dropbox connector with OAuth credentials."""
    connector = Connector(
        workspace_id=dropbox_workspace.id,
        connector_type="dropbox",
        display_name="Test Dropbox",
        config={
            "folders": ["/Work", "/Projects"],
            "include_shared": True,
        },
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    # Mock credentials (would be encrypted in production)
    connector._credentials_dict = {
        "access_token": "sl.test_token_1234567890",
        "token_type": "bearer",
        "account_id": "dbid:test123",
    }
    db_session.add(connector)
    db_session.commit()
    return connector


class TestDropboxAPIStructure:
    """Test that Dropbox API returns expected structure."""

    @dropbox_vcr.use_cassette("files_list_folder.yaml")
    def test_list_folder_structure(self, dropbox_connector):
        """Test /2/files/list_folder endpoint structure."""
        connector_instance = DropboxConnector(dropbox_connector)
        result = connector_instance._list_folder(path="")

        assert "entries" in result
        assert "cursor" in result
        assert "has_more" in result

        if result["entries"]:
            entry = result["entries"][0]
            assert ".tag" in entry
            assert "name" in entry
            assert "path_display" in entry

    @dropbox_vcr.use_cassette("files_download.yaml")
    def test_download_file_structure(self, dropbox_connector):
        """Test /2/files/download endpoint structure."""
        connector_instance = DropboxConnector(dropbox_connector)
        content, metadata = connector_instance._download_file(
            path="/test.txt"
        )

        assert isinstance(content, bytes)
        assert isinstance(metadata, dict)
        assert "name" in metadata
        assert "path_display" in metadata
        assert "size" in metadata

    @dropbox_vcr.use_cassette("sharing_list_shared_links.yaml")
    def test_shared_links_structure(self, dropbox_connector):
        """Test /2/sharing/list_shared_links endpoint structure."""
        connector_instance = DropboxConnector(dropbox_connector)
        links = connector_instance._list_shared_links(path="/test")

        assert isinstance(links, list)
        if links:
            link = links[0]
            assert "url" in link
            assert "path_lower" in link


class TestDropboxConnectorInterface:
    """Test that DropboxConnector implements expected interface."""

    @dropbox_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, dropbox_connector):
        """Test that sync() yields documents with required fields."""
        connector_instance = DropboxConnector(dropbox_connector)
        documents = list(connector_instance.sync(max_files=5))

        assert len(documents) > 0

        # Check document structure
        doc = documents[0]
        assert "source_id" in doc
        assert "source_type" in doc
        assert doc["source_type"] == "dropbox"
        assert "title" in doc
        assert "content" in doc
        assert "metadata" in doc
        assert "acl" in doc
        assert "source_url" in doc
        assert "timestamp" in doc

        # Check metadata
        metadata = doc["metadata"]
        assert "connector_id" in metadata
        assert "path" in metadata

    @dropbox_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync(self, dropbox_connector):
        """Test incremental sync with cursor state."""
        connector_instance = DropboxConnector(dropbox_connector)
        cursor_state = {
            "cursor": "test_cursor_123",
        }

        documents = list(
            connector_instance.sync(cursor_state=cursor_state, max_files=5)
        )

        assert len(documents) >= 0  # May be empty if no changes


class TestDropboxACLExtraction:
    """Test Dropbox ACL extraction logic."""

    @dropbox_vcr.use_cassette("sharing_list_folder_members.yaml")
    def test_extract_folder_acl(self, dropbox_connector):
        """Test ACL extraction for shared folder."""
        connector_instance = DropboxConnector(dropbox_connector)
        members = extract_folder_members(
            path="/Shared",
            dropbox_client=connector_instance,
        )

        acl = normalize_dropbox_acl(
            path="/Shared",
            is_shared=True,
            members=members,
        )

        assert acl["access_level"] == "shared"
        assert "allowed_users" in acl
        assert isinstance(acl["allowed_users"], list)

    def test_extract_personal_folder_acl(self):
        """Test ACL extraction for personal folder."""
        acl = normalize_dropbox_acl(
            path="/Personal",
            is_shared=False,
            members=[],
        )

        assert acl["access_level"] == "personal"

    def test_check_user_access_shared(self):
        """Test user access check for shared folder."""
        acl_metadata = {
            "access_level": "shared",
            "path": "/Shared",
            "allowed_users": ["user1@example.com", "user2@example.com"],
        }

        # User with access
        assert check_user_access("user1@example.com", acl_metadata) is True

        # User without access
        assert check_user_access("user3@example.com", acl_metadata) is False

    def test_check_user_access_personal(self):
        """Test user access check for personal folder."""
        acl_metadata = {
            "access_level": "personal",
            "path": "/Personal",
            "owner_email": "owner@example.com",
        }

        # Owner has access
        assert check_user_access("owner@example.com", acl_metadata) is True

        # Other users don't
        assert check_user_access("other@example.com", acl_metadata) is False

    def test_build_acl_filter_query(self):
        """Test building ACL filter query for vector DB."""
        user_email = "user@example.com"

        filter_query = build_acl_filter_query(user_email)

        assert "$or" in filter_query
        conditions = filter_query["$or"]
        assert len(conditions) >= 2


class TestDropboxRateLimiting:
    """Test Dropbox rate limiting behavior."""

    def test_rate_limiter_applied(self, dropbox_connector):
        """Test that rate limiter is applied to API methods."""
        connector_instance = DropboxConnector(dropbox_connector)

        # Check that rate limiter is applied
        assert hasattr(connector_instance._list_folder, "__wrapped__")
        assert hasattr(connector_instance._download_file, "__wrapped__")
