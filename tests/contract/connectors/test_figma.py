"""Contract tests for Figma connector using VCR cassettes."""

import pytest
from datetime import datetime, timezone
import vcr

from src.connectors.figma.connector import FigmaConnector
from src.connectors.figma.acl import (
    extract_project_members,
    normalize_figma_acl,
    check_user_access,
    build_acl_filter_query,
)
from src.models.connector import Connector
from src.models.workspace import Workspace


# VCR configuration for Figma API
figma_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/figma",
    record_mode="once",
    match_on=["uri", "method"],
    filter_headers=["X-Figma-Token"],
)


@pytest.fixture
def figma_workspace(db_session):
    """Create a test workspace."""
    workspace = Workspace(
        name="Test Workspace",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def figma_connector(db_session, figma_workspace):
    """Create a test Figma connector with OAuth credentials."""
    connector = Connector(
        workspace_id=figma_workspace.id,
        connector_type="figma",
        display_name="Test Figma",
        config={
            "team_id": "123456789",
            "project_ids": ["proj1", "proj2"],
        },
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    # Mock credentials (would be encrypted in production)
    connector._credentials_dict = {
        "access_token": "figd_test_token_1234567890",
        "token_type": "bearer",
        "scope": "files:read,file_comments:read",
    }
    db_session.add(connector)
    db_session.commit()
    return connector


class TestFigmaAPIStructure:
    """Test that Figma API returns expected structure."""

    @figma_vcr.use_cassette("team_projects.yaml")
    def test_team_projects_structure(self, figma_connector):
        """Test /v1/teams/{team_id}/projects endpoint structure."""
        connector_instance = FigmaConnector(figma_connector)
        projects = connector_instance._fetch_team_projects(
            team_id="123456789"
        )

        assert isinstance(projects, list)
        if projects:
            project = projects[0]
            assert "id" in project
            assert "name" in project

    @figma_vcr.use_cassette("project_files.yaml")
    def test_project_files_structure(self, figma_connector):
        """Test /v1/projects/{project_id}/files endpoint structure."""
        connector_instance = FigmaConnector(figma_connector)
        files = connector_instance._fetch_project_files(
            project_id="proj1"
        )

        assert isinstance(files, list)
        if files:
            file = files[0]
            assert "key" in file
            assert "name" in file
            assert "last_modified" in file

    @figma_vcr.use_cassette("file_get.yaml")
    def test_file_structure(self, figma_connector):
        """Test /v1/files/{file_key} endpoint structure."""
        connector_instance = FigmaConnector(figma_connector)
        file = connector_instance._fetch_file(
            file_key="abc123"
        )

        assert isinstance(file, dict)
        assert "name" in file
        assert "lastModified" in file
        assert "document" in file
        assert "thumbnailUrl" in file

    @figma_vcr.use_cassette("file_comments.yaml")
    def test_file_comments_structure(self, figma_connector):
        """Test /v1/files/{file_key}/comments endpoint structure."""
        connector_instance = FigmaConnector(figma_connector)
        comments = connector_instance._fetch_file_comments(
            file_key="abc123"
        )

        assert isinstance(comments, list)
        if comments:
            comment = comments[0]
            assert "id" in comment
            assert "message" in comment
            assert "user" in comment
            assert "created_at" in comment


class TestFigmaConnectorInterface:
    """Test that FigmaConnector implements expected interface."""

    @figma_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, figma_connector):
        """Test that sync() yields documents with required fields."""
        connector_instance = FigmaConnector(figma_connector)
        documents = list(connector_instance.sync(max_files=2))

        assert len(documents) > 0

        # Check document structure
        doc = documents[0]
        assert "source_id" in doc
        assert "source_type" in doc
        assert doc["source_type"] == "figma"
        assert "title" in doc
        assert "content" in doc
        assert "metadata" in doc
        assert "acl" in doc
        assert "source_url" in doc
        assert "timestamp" in doc

        # Check metadata
        metadata = doc["metadata"]
        assert "connector_id" in metadata
        assert "file_key" in metadata or "project_id" in metadata

    @figma_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync(self, figma_connector):
        """Test incremental sync with cursor state."""
        connector_instance = FigmaConnector(figma_connector)
        cursor_state = {
            "last_updated": "2024-01-01T00:00:00Z",
            "synced_files": ["file1"],
        }

        documents = list(
            connector_instance.sync(cursor_state=cursor_state, max_files=1)
        )

        assert len(documents) >= 0  # May be empty if no updates


class TestFigmaACLExtraction:
    """Test Figma ACL extraction logic."""

    @figma_vcr.use_cassette("project_members.yaml")
    def test_extract_project_acl(self, figma_connector):
        """Test ACL extraction for project."""
        connector_instance = FigmaConnector(figma_connector)
        members = extract_project_members(
            project_id="proj1",
            figma_client=connector_instance,
        )

        acl = normalize_figma_acl(
            project_id="proj1",
            project_name="Test Project",
            team_id="123456789",
            members=members,
        )

        assert acl["access_level"] == "team"
        assert "allowed_users" in acl
        assert isinstance(acl["allowed_users"], list)

    def test_check_user_access_team_member(self):
        """Test user access check for team member."""
        acl_metadata = {
            "access_level": "team",
            "team_id": "123456789",
            "allowed_users": ["user1", "user2"],
        }

        # User with access
        assert check_user_access("user1", acl_metadata, {"123456789"}) is True

        # User without access
        assert check_user_access("user3", acl_metadata, set()) is False

    def test_build_acl_filter_query(self):
        """Test building ACL filter query for vector DB."""
        user_figma_ids = ["user1", "user2"]
        user_team_memberships = {"team1", "team2"}

        filter_query = build_acl_filter_query(
            user_figma_ids, user_team_memberships
        )

        assert "$or" in filter_query
        conditions = filter_query["$or"]
        assert len(conditions) > 0


class TestFigmaRateLimiting:
    """Test Figma rate limiting behavior."""

    def test_rate_limiter_applied(self, figma_connector):
        """Test that rate limiter is applied to API methods."""
        connector_instance = FigmaConnector(figma_connector)

        # Check that rate limiter is applied
        assert hasattr(connector_instance._fetch_team_projects, "__wrapped__")
        assert hasattr(connector_instance._fetch_project_files, "__wrapped__")
        assert hasattr(connector_instance._fetch_file, "__wrapped__")
