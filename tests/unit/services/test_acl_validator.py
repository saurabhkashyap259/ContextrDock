"""Unit tests for ACL validator service."""

import pytest
from datetime import datetime

from src.services.acl_validator import ACLValidator, ACLResult


@pytest.fixture
def acl_validator():
    """Create ACL validator instance."""
    return ACLValidator()


@pytest.fixture
def sample_user():
    """Sample user with connector identities."""
    return {
        "id": 1,
        "email": "alice@company.com",
        "connector_identities": {
            "slack": {"user_id": "U123ABC", "team_id": "T456DEF"},
            "jira": {"account_id": "jira:alice-123"},
            "github": {"login": "alice-dev", "organizations": ["myorg"]},
            "confluence": {"account_id": "conf:alice-456"},
            "figma": {"user_id": "figma:alice-789", "teams": ["design-team"]},
            "dropbox": {"email": "alice@company.com"}
        }
    }


class TestACLValidatorBasics:
    """Test basic ACL validation functionality."""
    
    def test_public_document_allowed(self, acl_validator, sample_user):
        """Test that public documents are accessible to all users."""
        acl_metadata = {
            "access_level": "public",
            "connector_type": "slack"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
        assert result.reason == "Public access"
    
    def test_undefined_acl_denied_fail_closed(self, acl_validator, sample_user):
        """Test fail-closed: undefined ACL denies access."""
        acl_metadata = None
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False
        assert "undefined" in result.reason.lower() or "no acl" in result.reason.lower()
    
    def test_empty_acl_denied_fail_closed(self, acl_validator, sample_user):
        """Test fail-closed: empty ACL denies access."""
        acl_metadata = {}
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False
        assert "insufficient" in result.reason.lower() or "empty" in result.reason.lower()
    
    def test_missing_user_identity_denied(self, acl_validator):
        """Test that user without required identity is denied."""
        user = {
            "id": 2,
            "email": "bob@company.com",
            "connector_identities": {}  # No identities
        }
        
        acl_metadata = {
            "access_level": "restricted",
            "connector_type": "slack",
            "allowed_user_ids": ["U123ABC"]
        }
        
        result = acl_validator.check_access(user, acl_metadata)
        
        assert result.allowed is False
        assert "identity" in result.reason.lower()


class TestSlackACL:
    """Test Slack-specific ACL validation."""
    
    def test_slack_public_channel(self, acl_validator, sample_user):
        """Test access to public Slack channel."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "public",
            "channel_id": "C123",
            "channel_name": "general"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_slack_private_channel_member(self, acl_validator, sample_user):
        """Test access to private Slack channel for member."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_id": "C456",
            "allowed_user_ids": ["U123ABC", "U789XYZ"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
        assert "member" in result.reason.lower()
    
    def test_slack_private_channel_non_member(self, acl_validator, sample_user):
        """Test access denied to private Slack channel for non-member."""
        acl_metadata = {
            "connector_type": "slack",
            "access_level": "restricted",
            "channel_id": "C999",
            "allowed_user_ids": ["U999XXX", "U888YYY"]  # User not in list
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False
        assert "not a member" in result.reason.lower()


class TestJiraACL:
    """Test Jira-specific ACL validation."""
    
    def test_jira_public_project(self, acl_validator, sample_user):
        """Test access to public Jira project."""
        acl_metadata = {
            "connector_type": "jira",
            "access_level": "public",
            "project_key": "PROJ"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_jira_restricted_project_with_role(self, acl_validator, sample_user):
        """Test access to restricted Jira project with user having role."""
        acl_metadata = {
            "connector_type": "jira",
            "access_level": "restricted",
            "project_key": "ENG",
            "allowed_account_ids": ["jira:alice-123", "jira:bob-456"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_jira_restricted_project_without_role(self, acl_validator, sample_user):
        """Test access denied to restricted Jira project without role."""
        acl_metadata = {
            "connector_type": "jira",
            "access_level": "restricted",
            "project_key": "SECRET",
            "allowed_account_ids": ["jira:other-999"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False


class TestConfluenceACL:
    """Test Confluence-specific ACL validation."""
    
    def test_confluence_public_space(self, acl_validator, sample_user):
        """Test access to public Confluence space."""
        acl_metadata = {
            "connector_type": "confluence",
            "access_level": "public",
            "space_key": "DOCS"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_confluence_restricted_space_with_permission(self, acl_validator, sample_user):
        """Test access to restricted Confluence space with permission."""
        acl_metadata = {
            "connector_type": "confluence",
            "access_level": "restricted",
            "space_key": "ENG",
            "allowed_account_ids": ["conf:alice-456"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_confluence_restricted_space_without_permission(self, acl_validator, sample_user):
        """Test access denied to restricted Confluence space."""
        acl_metadata = {
            "connector_type": "confluence",
            "access_level": "restricted",
            "space_key": "EXEC",
            "allowed_account_ids": ["conf:exec-111", "conf:exec-222"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False


class TestGitHubACL:
    """Test GitHub-specific ACL validation."""
    
    def test_github_public_repo(self, acl_validator, sample_user):
        """Test access to public GitHub repository."""
        acl_metadata = {
            "connector_type": "github",
            "access_level": "public",
            "visibility": "public",
            "repository": "myorg/public-repo"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_github_private_repo_collaborator(self, acl_validator, sample_user):
        """Test access to private GitHub repo as collaborator."""
        acl_metadata = {
            "connector_type": "github",
            "access_level": "restricted",
            "visibility": "private",
            "repository": "myorg/private-repo",
            "collaborators": ["alice-dev", "bob-dev"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_github_private_repo_non_collaborator(self, acl_validator, sample_user):
        """Test access denied to private GitHub repo for non-collaborator."""
        acl_metadata = {
            "connector_type": "github",
            "access_level": "restricted",
            "visibility": "private",
            "repository": "myorg/secret-repo",
            "collaborators": ["other-user"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False
    
    def test_github_internal_repo_org_member(self, acl_validator, sample_user):
        """Test access to internal GitHub repo for org member."""
        acl_metadata = {
            "connector_type": "github",
            "access_level": "internal",
            "visibility": "internal",
            "repository": "myorg/internal-repo",
            "organization": "myorg"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True


class TestFigmaACL:
    """Test Figma-specific ACL validation."""
    
    def test_figma_team_member(self, acl_validator, sample_user):
        """Test access to Figma file for team member."""
        acl_metadata = {
            "connector_type": "figma",
            "access_level": "team",
            "team_id": "design-team",
            "allowed_users": ["figma:alice-789", "figma:bob-123"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_figma_team_non_member(self, acl_validator, sample_user):
        """Test access denied to Figma file for non-team member."""
        acl_metadata = {
            "connector_type": "figma",
            "access_level": "team",
            "team_id": "other-team",
            "allowed_users": ["figma:other-999"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False


class TestDropboxACL:
    """Test Dropbox-specific ACL validation."""
    
    def test_dropbox_personal_file_owner(self, acl_validator, sample_user):
        """Test access to personal Dropbox file for owner."""
        acl_metadata = {
            "connector_type": "dropbox",
            "access_level": "personal",
            "owner_email": "alice@company.com"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_dropbox_personal_file_non_owner(self, acl_validator, sample_user):
        """Test access denied to personal Dropbox file for non-owner."""
        acl_metadata = {
            "connector_type": "dropbox",
            "access_level": "personal",
            "owner_email": "bob@company.com"
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is False
    
    def test_dropbox_shared_file_member(self, acl_validator, sample_user):
        """Test access to shared Dropbox file for member."""
        acl_metadata = {
            "connector_type": "dropbox",
            "access_level": "shared",
            "shared_with": ["alice@company.com", "bob@company.com"]
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True
    
    def test_dropbox_public_link(self, acl_validator, sample_user):
        """Test access to Dropbox file with public link."""
        acl_metadata = {
            "connector_type": "dropbox",
            "access_level": "public_link",
            "has_shared_link": True
        }
        
        result = acl_validator.check_access(sample_user, acl_metadata)
        
        assert result.allowed is True


class TestBatchACLValidation:
    """Test batch ACL validation for performance."""
    
    def test_batch_validation(self, acl_validator, sample_user):
        """Test validating multiple ACLs in batch."""
        acl_list = [
            {"access_level": "public", "connector_type": "slack"},
            {"access_level": "restricted", "connector_type": "slack", 
             "allowed_user_ids": ["U123ABC"]},
            {"access_level": "restricted", "connector_type": "slack",
             "allowed_user_ids": ["U999XXX"]},
            {"access_level": "public", "connector_type": "jira"},
        ]
        
        results = acl_validator.batch_check_access(sample_user, acl_list)
        
        assert len(results) == 4
        assert results[0].allowed is True  # Public
        assert results[1].allowed is True  # User in list
        assert results[2].allowed is False  # User not in list
        assert results[3].allowed is True  # Public


class TestACLResult:
    """Test ACL result object."""
    
    def test_acl_result_allowed(self):
        """Test ACL result for allowed access."""
        result = ACLResult(allowed=True, reason="User is member")
        
        assert result.allowed is True
        assert result.reason == "User is member"
        assert bool(result) is True
    
    def test_acl_result_denied(self):
        """Test ACL result for denied access."""
        result = ACLResult(allowed=False, reason="Not a member")
        
        assert result.allowed is False
        assert result.reason == "Not a member"
        assert bool(result) is False
