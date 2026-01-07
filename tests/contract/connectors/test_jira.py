"""Contract tests for Jira connector.

These tests use VCR.py to record real API responses and verify connector behavior
against actual Jira Cloud API structure.
"""

import os
from datetime import datetime

import pytest
import vcr

from src.connectors.jira.connector import JiraConnector
from src.connectors.sdk import OAuth2Token
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document  # noqa: F401
from src.models.sync_run import SyncRun  # noqa: F401
from src.models.workspace import Workspace


# VCR configuration for Jira API
jira_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/jira",
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["Authorization"],
    decode_compressed_response=True,
)


@pytest.fixture
def jira_token() -> str:
    """Get Jira OAuth token from environment or use placeholder."""
    return os.getenv("JIRA_ACCESS_TOKEN", "placeholder-token")


@pytest.fixture
def jira_oauth_token(jira_token: str) -> OAuth2Token:
    """Create OAuth2Token for Jira."""
    return OAuth2Token(
        access_token=jira_token,
        token_type="Bearer",
        expires_in=3600,
        refresh_token=None,
        scope="read:jira-work read:jira-user",
        expires_at=datetime.now().timestamp() + 3600,
    )


@pytest.fixture
def jira_connector_def(db_session) -> ConnectorDefinition:
    """Create Jira connector definition."""
    conn_def = ConnectorDefinition(
        name="Jira",
        connector_type="jira",
        description="Jira Cloud connector",
        config_schema={},
        oauth_scopes=["read:jira-work", "read:jira-user"],
        supports_read=True,
        supports_write=False,
    )
    db_session.add(conn_def)
    db_session.commit()
    return conn_def


@pytest.fixture
def jira_connector_instance(
    db_session, jira_connector_def: ConnectorDefinition, jira_oauth_token: OAuth2Token
) -> Connector:
    """Create Jira connector instance."""
    workspace = Workspace(name="Test Workspace")
    db_session.add(workspace)
    db_session.commit()
    
    connector = Connector(
        connector_definition_id=jira_connector_def.id,
        workspace_id=workspace.id,
        name="Test Jira",
        config_json={"instance_url": "https://test-company.atlassian.net"},
        credentials_encrypted=b"test_encrypted_token",
        sync_schedule="6-hourly",
        is_active=True,
    )
    db_session.add(connector)
    db_session.commit()
    return connector


@pytest.fixture
def jira_connector(
    jira_connector_instance: Connector, jira_oauth_token: OAuth2Token
) -> JiraConnector:
    """Create JiraConnector instance with test credentials."""
    connector = JiraConnector(jira_connector_instance)
    connector._oauth_token = jira_oauth_token
    return connector


class TestJiraAPIStructure:
    """Test Jira API response structure matches our expectations."""

    @jira_vcr.use_cassette("issues_search.yaml")
    def test_issues_search_response_structure(self, jira_connector: JiraConnector):
        """Verify /search API response structure."""
        result = jira_connector._fetch_issues_page(max_results=10)

        assert "issues" in result
        assert "total" in result
        assert "startAt" in result
        assert "maxResults" in result

        if len(result["issues"]) > 0:
            issue = result["issues"][0]
            assert "key" in issue
            assert "id" in issue
            assert "fields" in issue

            fields = issue["fields"]
            assert "summary" in fields
            assert "status" in fields
            assert "project" in fields

    @jira_vcr.use_cassette("project_get.yaml")
    def test_project_response_structure(self, jira_connector: JiraConnector):
        """Verify /project/{key} API response structure."""
        # Use a test project key (should be in cassette)
        test_project_key = "TEST"

        result = jira_connector._fetch_project(test_project_key)

        assert "key" in result
        assert "name" in result
        assert "id" in result

    @jira_vcr.use_cassette("users_search.yaml")
    def test_users_search_response_structure(self, jira_connector: JiraConnector):
        """Verify /users/search API response structure."""
        result = jira_connector._fetch_users_page(max_results=10)

        assert isinstance(result, list)

        if len(result) > 0:
            user = result[0]
            assert "accountId" in user
            assert "displayName" in user


class TestJiraConnectorInterface:
    """Test JiraConnector implements ConnectorBase interface correctly."""

    def test_connector_has_required_methods(self, jira_connector: JiraConnector):
        """Verify JiraConnector implements all required methods."""
        assert hasattr(jira_connector, "sync")
        assert hasattr(jira_connector, "fetch_page")
        assert hasattr(jira_connector, "extract_acl")
        assert callable(jira_connector.sync)
        assert callable(jira_connector.fetch_page)
        assert callable(jira_connector.extract_acl)

    @jira_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, jira_connector: JiraConnector):
        """Verify sync() returns Document objects with required fields."""
        documents = []
        for doc in jira_connector.sync(max_issues=2):
            documents.append(doc)

        assert len(documents) > 0

        # Verify document structure
        for doc in documents:
            assert "source_id" in doc
            assert "source_type" in doc
            assert "content" in doc
            assert "metadata" in doc
            assert "acl_metadata" in doc

            # Jira-specific fields
            assert doc["source_type"] == "jira"
            if "comment" not in doc["source_id"]:
                # Issue document
                assert "issue_key" in doc["metadata"]
                assert "project_key" in doc["metadata"]

    @jira_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync_with_timestamp(self, jira_connector: JiraConnector):
        """Verify sync() respects last_sync_timestamp for incremental sync."""
        # First sync
        documents_first = []
        for doc in jira_connector.sync(max_issues=2):
            documents_first.append(doc)

        # Get cursor state
        cursor_state = jira_connector.get_cursor_state()

        # Second sync with cursor
        documents_second = []
        for doc in jira_connector.sync(cursor_state=cursor_state, max_issues=2):
            documents_second.append(doc)

        # Verify cursor state contains timestamp
        assert cursor_state is not None
        assert "last_sync_timestamp" in cursor_state


class TestJiraACLExtraction:
    """Test ACL metadata extraction from Jira documents."""

    def test_extract_acl_for_public_issue(self, jira_connector: JiraConnector):
        """Verify ACL extraction for issues without security level."""
        test_doc_metadata = {
            "issue_key": "PROJ-123",
            "project_key": "PROJ",
            "project_name": "Test Project",
        }

        acl = jira_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert acl["connector_type"] == "jira"
        assert acl["project_key"] == "PROJ"
        assert acl["access_level"] == "project"
        assert acl["requires_project_role"] is True

    def test_extract_acl_for_restricted_issue(self, jira_connector: JiraConnector):
        """Verify ACL extraction for issues with security level."""
        test_doc_metadata = {
            "issue_key": "PROJ-456",
            "project_key": "PROJ",
            "project_name": "Test Project",
            "security_level": "Confidential",
            "security_level_id": "10001",
        }

        acl = jira_connector.extract_acl(test_doc_metadata)

        assert acl is not None
        assert acl["access_level"] == "restricted"
        assert acl["security_level"] == "Confidential"
        assert acl["security_level_id"] == "10001"
        assert "allowed_users" in acl


class TestJiraRateLimiting:
    """Test Jira connector respects rate limits."""

    def test_connector_has_rate_limiter(self, jira_connector: JiraConnector):
        """Verify JiraConnector has rate limiter configured."""
        # Check if _fetch methods have rate limiting decorator
        assert hasattr(jira_connector._fetch_issues_page, "__wrapped__")
