"""Confluence ACL extraction utilities.

Extracts access control metadata from Confluence documents for permission-aware retrieval.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_space_permissions(space_key: str, confluence_client: Any) -> list[dict[str, Any]]:
    """Fetch space permissions for users and groups.

    Args:
        space_key: Confluence space key
        confluence_client: Authenticated Confluence client

    Returns:
        List of permissions with user/group lists
    """
    try:
        # Fetch space permissions
        response = confluence_client.get(f"/rest/api/space/{space_key}/permission")
        if response.status_code == 200:
            permissions_data = response.json()

            permissions = []
            for permission in permissions_data:
                permission_type = permission.get("type")  # view, edit, admin
                subjects = permission.get("subjects", {})

                users = []
                for user in subjects.get("user", {}).get("results", []):
                    users.append({
                        "account_id": user.get("accountId"),
                        "display_name": user.get("displayName"),
                    })

                groups = []
                for group in subjects.get("group", {}).get("results", []):
                    groups.append({
                        "name": group.get("name"),
                    })

                permissions.append({
                    "permission_type": permission_type,
                    "users": users,
                    "groups": groups,
                })

            return permissions
    except Exception as e:
        logger.warning(f"Failed to fetch space permissions for {space_key}: {e}")

    return []


def extract_page_restriction_users(page_id: str, confluence_client: Any) -> list[str]:
    """Fetch users with read access to a restricted page.

    Args:
        page_id: Confluence page ID
        confluence_client: Authenticated Confluence client

    Returns:
        List of account IDs with access
    """
    try:
        response = confluence_client.get(
            f"/rest/api/content/{page_id}/restriction",
            params={"expand": "restrictions.user"}
        )
        if response.status_code == 200:
            restrictions_data = response.json()
            read_restrictions = restrictions_data.get("read", {})
            user_results = read_restrictions.get("restrictions", {}).get("user", {}).get("results", [])

            return [user.get("accountId") for user in user_results if user.get("accountId")]
    except Exception as e:
        logger.warning(f"Failed to fetch page restrictions for {page_id}: {e}")

    return []


def normalize_confluence_acl(
    space_key: str,
    space_name: str,
    instance_url: str,
    space_type: str = "global",
    restricted_users: Optional[list[str]] = None,
    restricted_groups: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Normalize Confluence ACL metadata to standard format.

    Args:
        space_key: Confluence space key
        space_name: Space display name
        instance_url: Confluence instance URL
        space_type: Space type (global, personal)
        restricted_users: List of account IDs with page-level access
        restricted_groups: List of group names with page-level access

    Returns:
        Normalized ACL metadata dict
    """
    acl = {
        "connector_type": "confluence",
        "instance_url": instance_url,
        "space_key": space_key,
        "space_name": space_name,
        "space_type": space_type,
    }

    if restricted_users or restricted_groups:
        # Page-level restrictions
        acl["access_level"] = "restricted"
        acl["allowed_users"] = restricted_users or []
        acl["allowed_groups"] = restricted_groups or []
    else:
        # Space-level access
        acl["access_level"] = "space"
        acl["requires_space_permission"] = True

        # Personal spaces are more restrictive
        if space_type == "personal":
            acl["access_level"] = "personal"

    return acl


def check_user_access(
    user_account_id: str,
    acl_metadata: dict[str, Any],
    user_space_permissions: dict[str, list[str]],  # space_key -> [permission_types]
    user_groups: set[str],
) -> bool:
    """Check if user has access to a Confluence document.

    Args:
        user_account_id: User's Confluence account ID
        acl_metadata: ACL metadata from document
        user_space_permissions: Mapping of user's permissions per space
        user_groups: Set of group names user belongs to

    Returns:
        True if user has access, False otherwise
    """
    space_key = acl_metadata.get("space_key")
    access_level = acl_metadata.get("access_level")

    # Check if user has space permissions
    space_perms = user_space_permissions.get(space_key, [])
    if not space_perms and access_level != "restricted":
        return False

    if access_level == "restricted":
        # Page-level restrictions - check explicit lists
        allowed_users = acl_metadata.get("allowed_users", [])
        allowed_groups = acl_metadata.get("allowed_groups", [])

        # Check if user is in allowed users list
        if user_account_id in allowed_users:
            return True

        # Check if user is in any allowed groups
        if any(group in user_groups for group in allowed_groups):
            return True

        return False
    elif access_level == "space" or access_level == "personal":
        # Space-level access - user needs view permission
        return "view" in space_perms or "admin" in space_perms

    return False


def build_acl_filter_query(
    user_account_id: str,
    user_space_permissions: dict[str, list[str]],  # space_key -> [permission_types]
    user_groups: set[str],
) -> dict[str, Any]:
    """Build vector database filter for Confluence ACL enforcement.

    Args:
        user_account_id: User's Confluence account ID
        user_space_permissions: Mapping of user's permissions per space
        user_groups: Set of group names user belongs to

    Returns:
        Filter query dict for vector database
    """
    conditions = []

    for space_key, perms in user_space_permissions.items():
        # Only include spaces where user has view or admin permission
        if "view" not in perms and "admin" not in perms:
            continue

        # Space-level access (no restrictions)
        conditions.append({
            "space_key": space_key,
            "access_level": "space",
        })

        # Personal space access
        conditions.append({
            "space_key": space_key,
            "access_level": "personal",
        })

        # Restricted pages where user is in allowed list
        conditions.append({
            "space_key": space_key,
            "access_level": "restricted",
            "allowed_users": {"$contains": user_account_id},
        })

        # Restricted pages where user's group is in allowed list
        if user_groups:
            for group in user_groups:
                conditions.append({
                    "space_key": space_key,
                    "access_level": "restricted",
                    "allowed_groups": {"$contains": group},
                })

    # Combine with OR logic
    return {"$or": conditions} if len(conditions) > 1 else (conditions[0] if conditions else {})
