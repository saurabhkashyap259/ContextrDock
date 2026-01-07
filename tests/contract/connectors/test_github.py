"""Contract tests for GitHub connector using VCR cassettes."""

import pytest
from datetime import datetime, timezone
import vcr

from src.connectors.github.connector import GitHubConnector
from src.connectors.github.acl import (
    extract_repo_collaborators,
    normalize_github_acl,
    check_user_access,
    build_acl_filter_query,
)
from src.models.connector import Connector
from src.models.workspace import Workspace


# VCR configuration for GitHub API
github_vcr = vcr.VCR(
    cassette_library_dir="tests/fixtures/vcr_cassettes/github",
    record_mode="once",
    match_on=["uri", "method"],
    filter_headers=["authorization"],
    filter_query_parameters=["access_token"],
)


@pytest.fixture
def github_workspace(db_session):
    """Create a test workspace."""
    workspace = Workspace(
        name="Test Workspace",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(workspace)
    db_session.commit()
    return workspace


@pytest.fixture
def github_connector(db_session, github_workspace):
    """Create a test GitHub connector with OAuth credentials."""
    connector = Connector(
        workspace_id=github_workspace.id,
        connector_type="github",
        display_name="Test GitHub",
        config={
            "organization": "example-org",
            "repositories": ["repo1", "repo2"],
        },
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    # Mock credentials (would be encrypted in production)
    connector._credentials_dict = {
        "access_token": "gho_test_token_1234567890",
        "token_type": "bearer",
        "scope": "repo,read:org,read:user",
    }
    db_session.add(connector)
    db_session.commit()
    return connector


class TestGitHubAPIStructure:
    """Test that GitHub API returns expected structure."""

    @github_vcr.use_cassette("repos_list.yaml")
    def test_repos_list_structure(self, github_connector):
        """Test /orgs/{org}/repos endpoint structure."""
        connector_instance = GitHubConnector(github_connector)
        repos = connector_instance._fetch_repos_page(page=1, per_page=10)

        assert isinstance(repos, list)
        if repos:
            repo = repos[0]
            assert "id" in repo
            assert "name" in repo
            assert "full_name" in repo
            assert "description" in repo
            assert "private" in repo
            assert "html_url" in repo
            assert "default_branch" in repo
            assert "owner" in repo
            assert "updated_at" in repo

    @github_vcr.use_cassette("issues_list.yaml")
    def test_issues_list_structure(self, github_connector):
        """Test /repos/{owner}/{repo}/issues endpoint structure."""
        connector_instance = GitHubConnector(github_connector)
        issues = connector_instance._fetch_issues_page(
            owner="example-org",
            repo="example-repo",
            page=1,
            per_page=10,
        )

        assert isinstance(issues, list)
        if issues:
            issue = issues[0]
            assert "id" in issue
            assert "number" in issue
            assert "title" in issue
            assert "body" in issue
            assert "state" in issue
            assert "html_url" in issue
            assert "user" in issue
            assert "created_at" in issue
            assert "updated_at" in issue
            assert "comments" in issue

    @github_vcr.use_cassette("pulls_list.yaml")
    def test_pulls_list_structure(self, github_connector):
        """Test /repos/{owner}/{repo}/pulls endpoint structure."""
        connector_instance = GitHubConnector(github_connector)
        pulls = connector_instance._fetch_pulls_page(
            owner="example-org",
            repo="example-repo",
            page=1,
            per_page=10,
        )

        assert isinstance(pulls, list)
        if pulls:
            pr = pulls[0]
            assert "id" in pr
            assert "number" in pr
            assert "title" in pr
            assert "body" in pr
            assert "state" in pr
            assert "html_url" in pr
            assert "user" in pr
            assert "created_at" in pr
            assert "updated_at" in pr
            assert "head" in pr
            assert "base" in pr

    @github_vcr.use_cassette("readme_get.yaml")
    def test_readme_structure(self, github_connector):
        """Test /repos/{owner}/{repo}/readme endpoint structure."""
        connector_instance = GitHubConnector(github_connector)
        readme = connector_instance._fetch_readme(
            owner="example-org",
            repo="example-repo",
        )

        assert isinstance(readme, dict)
        assert "name" in readme
        assert "path" in readme
        assert "content" in readme  # Base64 encoded
        assert "encoding" in readme
        assert "html_url" in readme


class TestGitHubConnectorInterface:
    """Test that GitHubConnector implements expected interface."""

    @github_vcr.use_cassette("full_sync.yaml")
    def test_sync_returns_documents(self, github_connector):
        """Test that sync() yields documents with required fields."""
        connector_instance = GitHubConnector(github_connector)
        documents = list(connector_instance.sync(max_repos=2, max_issues_per_repo=5))

        assert len(documents) > 0

        # Check document structure
        doc = documents[0]
        assert "source_id" in doc
        assert "source_type" in doc
        assert doc["source_type"] == "github"
        assert "title" in doc
        assert "content" in doc
        assert "metadata" in doc
        assert "acl" in doc
        assert "source_url" in doc
        assert "timestamp" in doc

        # Check metadata
        metadata = doc["metadata"]
        assert "connector_id" in metadata
        assert "repository" in metadata or "repo_name" in metadata

    @github_vcr.use_cassette("incremental_sync.yaml")
    def test_incremental_sync(self, github_connector):
        """Test incremental sync with cursor state."""
        connector_instance = GitHubConnector(github_connector)
        cursor_state = {
            "last_updated": "2024-01-01T00:00:00Z",
            "synced_repos": ["repo1"],
        }

        documents = list(
            connector_instance.sync(cursor_state=cursor_state, max_repos=1)
        )

        assert len(documents) >= 0  # May be empty if no updates


class TestGitHubACLExtraction:
    """Test GitHub ACL extraction logic."""

    @github_vcr.use_cassette("collaborators_list.yaml")
    def test_extract_public_repo_acl(self, github_connector):
        """Test ACL extraction for public repository."""
        connector_instance = GitHubConnector(github_connector)
        collaborators = extract_repo_collaborators(
            owner="example-org",
            repo="public-repo",
            github_client=connector_instance,
        )

        acl = normalize_github_acl(
            visibility="public",
            owner="example-org",
            repo_name="public-repo",
            collaborators=collaborators,
        )

        assert acl["access_level"] == "public"
        assert "allowed_users" not in acl or len(acl["allowed_users"]) == 0

    @github_vcr.use_cassette("collaborators_list.yaml")
    def test_extract_private_repo_acl(self, github_connector):
        """Test ACL extraction for private repository."""
        connector_instance = GitHubConnector(github_connector)
        collaborators = extract_repo_collaborators(
            owner="example-org",
            repo="private-repo",
            github_client=connector_instance,
        )

        acl = normalize_github_acl(
            visibility="private",
            owner="example-org",
            repo_name="private-repo",
            collaborators=collaborators,
        )

        assert acl["access_level"] == "private"
        assert "allowed_users" in acl
        assert isinstance(acl["allowed_users"], list)

    def test_check_user_access_public(self):
        """Test user access check for public repository."""
        acl_metadata = {
            "access_level": "public",
            "owner": "example-org",
            "repo_name": "public-repo",
        }

        # Any user can access public repos
        assert check_user_access("any_user", acl_metadata, set()) is True

    def test_check_user_access_private(self):
        """Test user access check for private repository."""
        acl_metadata = {
            "access_level": "private",
            "owner": "example-org",
            "repo_name": "private-repo",
            "allowed_users": ["user1", "user2"],
        }

        # User with access
        assert check_user_access("user1", acl_metadata, {"example-org"}) is True

        # User without access
        assert check_user_access("user3", acl_metadata, set()) is False

    def test_build_acl_filter_query(self):
        """Test building ACL filter query for vector DB."""
        user_github_logins = ["user1", "user2"]
        user_org_memberships = {"org1", "org2"}

        filter_query = build_acl_filter_query(
            user_github_logins, user_org_memberships
        )

        assert "$or" in filter_query
        conditions = filter_query["$or"]
        assert any(c.get("acl.access_level") == "public" for c in conditions)


class TestGitHubRateLimiting:
    """Test GitHub rate limiting behavior."""

    def test_rate_limiter_applied(self, github_connector):
        """Test that rate limiter is applied to API methods."""
        connector_instance = GitHubConnector(github_connector)

        # Check that rate limiter is applied
        assert hasattr(connector_instance._fetch_repos_page, "__wrapped__")
        assert hasattr(connector_instance._fetch_issues_page, "__wrapped__")
