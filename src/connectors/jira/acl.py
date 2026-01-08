"""Jira ACL extraction utilities.

Extracts access control metadata from Jira documents for permission-aware retrieval.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_project_roles(project_key: str, jira_client: Any) -> list[dict[str, Any]]:
    """Fetch project roles and members.

    Args:
        project_key: Jira project key
        jira_client: Authenticated Jira client

    Returns:
        List of roles with member lists
    """
    try:
        # Fetch project roles
        response = jira_client.get(f"/rest/api/3/project/{project_key}/role")
        if response.status_code == 200:
            roles_data = response.json()

            roles = []
            for role_name, role_url in roles_data.items():
                # Fetch role members
                role_response = jira_client.get(role_url)
                if role_response.status_code == 200:
                    role_detail = role_response.json()
                    actors = role_detail.get("actors", [])

                    members = []
                    for actor in actors:
                        actor_type = actor.get("type")
                        if actor_type == "atlassian-user-role-actor":
                            # Individual user
                            members.append({
                                "account_id": actor.get("actorUser", {}).get("accountId"),
                                "display_name": actor.get("displayName"),
                            })
                        elif actor_type == "atlassian-group-role-actor":
                            # Group - would need to expand members
                            members.append({
                                "group_name": actor.get("displayName"),
                                "type": "group",
                            })

                    roles.append({
                        "role_name": role_name,
                        "role_id": role_detail.get("id"),
                        "members": members,
                    })

            return roles
    except Exception as e:
        logger.warning(f"Failed to fetch project roles for {project_key}: {e}")

    return []


def extract_security_level_users(
    security_level_id: str, project_key: str, jira_client: Any
) -> list[str]:
    """Fetch users with access to a security level.

    Args:
        security_level_id: Jira security level ID
        project_key: Jira project key
        jira_client: Authenticated Jira client

    Returns:
        List of account IDs with access
    """
    try:
        # Note: Jira doesn't have a direct API to get security level members
        # This would typically require admin permissions and a custom query
        # For MVP, return empty list and handle at query time
        logger.warning(
            f"Security level {security_level_id} access check requires admin API"
        )
    except Exception as e:
        logger.warning(
            f"Failed to fetch security level users for {security_level_id}: {e}"
        )

    return []


def normalize_jira_acl(
    project_key: str,
    project_name: str,
    instance_url: str,
    security_level: Optional[str] = None,
    security_level_id: Optional[str] = None,
    allowed_users: Optional[list[str]] = None,
    project_roles: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Normalize Jira ACL metadata to standard format.

    Args:
        project_key: Jira project key
        project_name: Project display name
        instance_url: Jira instance URL
        security_level: Security level name (if restricted)
        security_level_id: Security level ID
        allowed_users: List of account IDs with access (for security levels)
        project_roles: List of role names with access

    Returns:
        Normalized ACL metadata dict
    """
    acl = {
        "connector_type": "jira",
        "instance_url": instance_url,
        "project_key": project_key,
        "project_name": project_name,
    }

    if security_level:
        # Restricted access via security level
        acl["access_level"] = "restricted"
        acl["security_level"] = security_level
        acl["security_level_id"] = security_level_id
        acl["allowed_users"] = allowed_users or []
    else:
        # Project-level access
        acl["access_level"] = "project"
        acl["requires_project_role"] = True
        acl["required_roles"] = project_roles or ["users"]  # Default to basic users role

    return acl


def check_user_access(
    user_account_id: str,
    acl_metadata: dict[str, Any],
    user_project_roles: dict[str, list[str]],  # project_key -> [role_names]
) -> bool:
    """Check if user has access to a Jira document.

    Args:
        user_account_id: User's Jira account ID
        acl_metadata: ACL metadata from document
        user_project_roles: Mapping of user's roles per project

    Returns:
        True if user has access, False otherwise
    """
    project_key = acl_metadata.get("project_key")
    access_level = acl_metadata.get("access_level")

    # Check if user has any role in the project
    user_roles = user_project_roles.get(project_key, [])
    if not user_roles:
        return False

    if access_level == "restricted":
        # Security level - check explicit user list
        allowed_users = acl_metadata.get("allowed_users", [])
        return user_account_id in allowed_users
    elif access_level == "project":
        # Project-level - user needs any project role
        required_roles = acl_metadata.get("required_roles", [])
        if not required_roles:
            # No specific roles required - any project member has access
            return True
        # Check if user has any of the required roles
        return any(role in user_roles for role in required_roles)

    return False


def build_acl_filter_query(
    user_account_id: str,
    user_project_roles: dict[str, list[str]],  # project_key -> [role_names]
) -> dict[str, Any]:
    """Build vector database filter for Jira ACL enforcement.

    Args:
        user_account_id: User's Jira account ID
        user_project_roles: Mapping of user's roles per project

    Returns:
        Filter query dict for vector database
    """
    conditions = []

    for project_key, roles in user_project_roles.items():
        # Project-level access (no security level)
        conditions.append({
            "project_key": project_key,
            "access_level": "project",
        })

        # Restricted access where user is in allowed list
        conditions.append({
            "project_key": project_key,
            "access_level": "restricted",
            "allowed_users": {"$contains": user_account_id},
        })

    # Combine with OR logic
    return {"$or": conditions} if len(conditions) > 1 else (conditions[0] if conditions else {})
