"""ACL validator service for permission-aware retrieval.

This service validates user access to documents based on ACL metadata
extracted from source connectors. Implements fail-closed security: if ACL
is undefined or cannot be validated, access is denied.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ACLResult:
    """Result of an ACL validation check."""
    
    allowed: bool
    reason: str
    
    def __bool__(self) -> bool:
        """Allow using ACLResult in boolean context."""
        return self.allowed


class ACLValidator:
    """Validates user access to documents based on ACL metadata.
    
    Implements fail-closed security: if ACL is undefined, malformed, or
    user identity is missing, access is denied by default.
    
    Supports ACL formats from all connectors:
    - Slack: channel members, public channels
    - Jira: project roles, issue visibility
    - Confluence: space permissions, page restrictions
    - GitHub: repository collaborators, organization members
    - Figma: team members, project permissions
    - Dropbox: file owners, shared folders, public links
    """
    
    def __init__(self):
        """Initialize ACL validator."""
        self._connector_validators = {
            "slack": self._validate_slack_acl,
            "jira": self._validate_jira_acl,
            "confluence": self._validate_confluence_acl,
            "github": self._validate_github_acl,
            "figma": self._validate_figma_acl,
            "dropbox": self._validate_dropbox_acl,
        }
    
    def check_access(
        self,
        user: Dict[str, Any],
        acl_metadata: Optional[Dict[str, Any]]
    ) -> ACLResult:
        """Check if user has access to document with given ACL.
        
        Args:
            user: User object with connector_identities
            acl_metadata: ACL metadata from document chunk
            
        Returns:
            ACLResult with allowed flag and reason
        """
        # Fail-closed: No ACL means no access
        if acl_metadata is None:
            logger.debug(f"Access denied for user {user.get('id')}: ACL undefined")
            return ACLResult(allowed=False, reason="ACL undefined")
        
        # Fail-closed: Empty ACL means no access
        if not acl_metadata:
            logger.debug(f"Access denied for user {user.get('id')}: ACL empty")
            return ACLResult(allowed=False, reason="ACL empty - insufficient metadata")
        
        # Check for public access
        access_level = acl_metadata.get("access_level", "").lower()
        if access_level == "public":
            return ACLResult(allowed=True, reason="Public access")
        
        # Get connector type
        connector_type = acl_metadata.get("connector_type")
        if not connector_type:
            return ACLResult(
                allowed=False,
                reason="ACL missing connector_type"
            )
        
        # Get connector-specific validator
        validator = self._connector_validators.get(connector_type)
        if not validator:
            logger.warning(
                f"Unknown connector type: {connector_type}, denying access"
            )
            return ACLResult(
                allowed=False,
                reason=f"Unknown connector type: {connector_type}"
            )
        
        # Validate with connector-specific logic
        return validator(user, acl_metadata)
    
    def batch_check_access(
        self,
        user: Dict[str, Any],
        acl_list: List[Dict[str, Any]]
    ) -> List[ACLResult]:
        """Check access for multiple ACLs in batch.
        
        Args:
            user: User object with connector_identities
            acl_list: List of ACL metadata dictionaries
            
        Returns:
            List of ACLResult objects
        """
        return [self.check_access(user, acl) for acl in acl_list]
    
    def _get_user_identity(
        self,
        user: Dict[str, Any],
        connector_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get user's identity for specific connector.
        
        Args:
            user: User object with connector_identities
            connector_type: Type of connector (slack, jira, etc.)
            
        Returns:
            User's identity dict for connector, or None if not found
        """
        connector_identities = user.get("connector_identities", {})
        return connector_identities.get(connector_type)
    
    def _validate_slack_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate Slack ACL.
        
        Slack ACL format:
        {
            "connector_type": "slack",
            "access_level": "public" | "restricted",
            "channel_id": "C123",
            "channel_name": "general",
            "allowed_user_ids": ["U123", "U456"]  # For private channels
        }
        """
        identity = self._get_user_identity(user, "slack")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no Slack identity"
            )
        
        user_id = identity.get("user_id")
        if not user_id:
            return ACLResult(
                allowed=False,
                reason="Slack identity missing user_id"
            )
        
        # Check if user is in allowed list for restricted channels
        access_level = acl_metadata.get("access_level", "").lower()
        if access_level == "restricted":
            allowed_user_ids = acl_metadata.get("allowed_user_ids", [])
            if user_id in allowed_user_ids:
                return ACLResult(
                    allowed=True,
                    reason=f"User is member of channel {acl_metadata.get('channel_name', 'unknown')}"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User is not a member of private channel"
                )
        
        return ACLResult(allowed=False, reason="Insufficient Slack ACL metadata")
    
    def _validate_jira_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate Jira ACL.
        
        Jira ACL format:
        {
            "connector_type": "jira",
            "access_level": "public" | "restricted",
            "project_key": "PROJ",
            "allowed_account_ids": ["jira:123", "jira:456"]
        }
        """
        identity = self._get_user_identity(user, "jira")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no Jira identity"
            )
        
        account_id = identity.get("account_id")
        if not account_id:
            return ACLResult(
                allowed=False,
                reason="Jira identity missing account_id"
            )
        
        # Check if user is in allowed list
        access_level = acl_metadata.get("access_level", "").lower()
        if access_level == "restricted":
            allowed_account_ids = acl_metadata.get("allowed_account_ids", [])
            if account_id in allowed_account_ids:
                return ACLResult(
                    allowed=True,
                    reason=f"User has access to project {acl_metadata.get('project_key', 'unknown')}"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User does not have access to Jira project"
                )
        
        return ACLResult(allowed=False, reason="Insufficient Jira ACL metadata")
    
    def _validate_confluence_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate Confluence ACL.
        
        Confluence ACL format:
        {
            "connector_type": "confluence",
            "access_level": "public" | "restricted",
            "space_key": "DOCS",
            "allowed_account_ids": ["conf:123", "conf:456"]
        }
        """
        identity = self._get_user_identity(user, "confluence")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no Confluence identity"
            )
        
        account_id = identity.get("account_id")
        if not account_id:
            return ACLResult(
                allowed=False,
                reason="Confluence identity missing account_id"
            )
        
        # Check if user is in allowed list
        access_level = acl_metadata.get("access_level", "").lower()
        if access_level == "restricted":
            allowed_account_ids = acl_metadata.get("allowed_account_ids", [])
            if account_id in allowed_account_ids:
                return ACLResult(
                    allowed=True,
                    reason=f"User has access to space {acl_metadata.get('space_key', 'unknown')}"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User does not have access to Confluence space"
                )
        
        return ACLResult(allowed=False, reason="Insufficient Confluence ACL metadata")
    
    def _validate_github_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate GitHub ACL.
        
        GitHub ACL format:
        {
            "connector_type": "github",
            "access_level": "public" | "internal" | "restricted",
            "visibility": "public" | "internal" | "private",
            "repository": "owner/repo",
            "organization": "myorg",
            "collaborators": ["alice-dev", "bob-dev"]
        }
        """
        identity = self._get_user_identity(user, "github")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no GitHub identity"
            )
        
        login = identity.get("login")
        if not login:
            return ACLResult(
                allowed=False,
                reason="GitHub identity missing login"
            )
        
        access_level = acl_metadata.get("access_level", "").lower()
        
        # Internal repos: check org membership
        if access_level == "internal":
            org = acl_metadata.get("organization")
            user_orgs = identity.get("organizations", [])
            if org in user_orgs:
                return ACLResult(
                    allowed=True,
                    reason=f"User is member of organization {org}"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User is not member of organization"
                )
        
        # Private repos: check collaborator list
        if access_level == "restricted":
            collaborators = acl_metadata.get("collaborators", [])
            if login in collaborators:
                return ACLResult(
                    allowed=True,
                    reason=f"User is collaborator on {acl_metadata.get('repository', 'unknown')}"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User is not a collaborator on repository"
                )
        
        return ACLResult(allowed=False, reason="Insufficient GitHub ACL metadata")
    
    def _validate_figma_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate Figma ACL.
        
        Figma ACL format:
        {
            "connector_type": "figma",
            "access_level": "team",
            "team_id": "design-team",
            "allowed_users": ["figma:123", "figma:456"]
        }
        """
        identity = self._get_user_identity(user, "figma")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no Figma identity"
            )
        
        user_id = identity.get("user_id")
        if not user_id:
            return ACLResult(
                allowed=False,
                reason="Figma identity missing user_id"
            )
        
        # Check if user is in allowed list
        allowed_users = acl_metadata.get("allowed_users", [])
        if user_id in allowed_users:
            return ACLResult(
                allowed=True,
                reason=f"User is member of team {acl_metadata.get('team_id', 'unknown')}"
            )
        else:
            return ACLResult(
                allowed=False,
                reason="User is not a member of Figma team"
            )
    
    def _validate_dropbox_acl(
        self,
        user: Dict[str, Any],
        acl_metadata: Dict[str, Any]
    ) -> ACLResult:
        """Validate Dropbox ACL.
        
        Dropbox ACL format:
        {
            "connector_type": "dropbox",
            "access_level": "personal" | "shared" | "public_link",
            "owner_email": "alice@company.com",
            "shared_with": ["alice@company.com", "bob@company.com"],
            "has_shared_link": true
        }
        """
        identity = self._get_user_identity(user, "dropbox")
        if not identity:
            return ACLResult(
                allowed=False,
                reason="User has no Dropbox identity"
            )
        
        user_email = identity.get("email")
        if not user_email:
            return ACLResult(
                allowed=False,
                reason="Dropbox identity missing email"
            )
        
        access_level = acl_metadata.get("access_level", "").lower()
        
        # Public link: anyone can access
        if access_level == "public_link" and acl_metadata.get("has_shared_link"):
            return ACLResult(
                allowed=True,
                reason="File has public shared link"
            )
        
        # Personal file: only owner can access
        if access_level == "personal":
            owner_email = acl_metadata.get("owner_email")
            if user_email == owner_email:
                return ACLResult(
                    allowed=True,
                    reason="User is file owner"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="User is not file owner"
                )
        
        # Shared file: check shared_with list
        if access_level == "shared":
            shared_with = acl_metadata.get("shared_with", [])
            if user_email in shared_with:
                return ACLResult(
                    allowed=True,
                    reason="File is shared with user"
                )
            else:
                return ACLResult(
                    allowed=False,
                    reason="File is not shared with user"
                )
        
        return ACLResult(allowed=False, reason="Insufficient Dropbox ACL metadata")
