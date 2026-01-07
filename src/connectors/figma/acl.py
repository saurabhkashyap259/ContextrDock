"""ACL extraction and permission checking for Figma files."""

from typing import Any, Dict, List, Optional, Set


def extract_project_members(
    project_id: str,
    figma_client: Any,
) -> List[Dict[str, Any]]:
    """Fetch members for a project.

    Args:
        project_id: Figma project ID
        figma_client: FigmaConnector instance

    Returns:
        List of member dicts with user info and permissions
    """
    try:
        headers = figma_client._get_auth_headers()
        url = f"{figma_client.BASE_URL}/v1/projects/{project_id}"

        response = figma_client._rate_limited_request(
            "GET", url, headers=headers
        )
        response.raise_for_status()

        project_data = response.json()

        # Extract members from project data
        members = []
        project = project_data.get("project", {})

        # Team members with access
        if "members" in project:
            for member in project["members"]:
                members.append({
                    "id": member.get("id"),
                    "handle": member.get("handle"),
                    "role": member.get("role"),
                })

        return members
    except Exception:
        # If we can't fetch members, return empty list
        return []


def normalize_figma_acl(
    project_id: str,
    project_name: str,
    team_id: str,
    members: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Normalize Figma ACL to standard format.

    Args:
        project_id: Figma project ID
        project_name: Project name
        team_id: Figma team ID
        members: List of member dicts with id, handle, role

    Returns:
        Normalized ACL dict with access_level, team_id, allowed_users
    """
    if members is None:
        members = []

    allowed_users = []
    for member in members:
        # Include members with viewer, editor, or admin roles
        role = member.get("role", "viewer")
        if role in ["viewer", "editor", "admin", "owner"]:
            user_id = member.get("id")
            if user_id:
                allowed_users.append(user_id)

    return {
        "access_level": "team",
        "team_id": team_id,
        "project_id": project_id,
        "project_name": project_name,
        "allowed_users": allowed_users,
    }


def check_user_access(
    user_figma_id: str,
    acl_metadata: Dict[str, Any],
    user_team_memberships: Set[str],
) -> bool:
    """Check if user has access to a Figma document.

    Args:
        user_figma_id: User's Figma user ID
        acl_metadata: ACL metadata from document
        user_team_memberships: Set of team IDs user belongs to

    Returns:
        True if user has access, False otherwise
    """
    access_level = acl_metadata.get("access_level")

    # Team-level access
    if access_level == "team":
        team_id = acl_metadata.get("team_id")

        # Check if user is member of team
        if team_id in user_team_memberships:
            return True

        # Check if user is in explicit allowed list
        allowed_users = acl_metadata.get("allowed_users", [])
        if user_figma_id in allowed_users:
            return True

        return False

    # Default deny
    return False


def build_acl_filter_query(
    user_figma_ids: List[str],
    user_team_memberships: Set[str],
) -> Dict[str, Any]:
    """Build vector database filter query for Figma ACL.

    Args:
        user_figma_ids: List of user's Figma user IDs (may have multiple)
        user_team_memberships: Set of team IDs user belongs to

    Returns:
        Filter query dict for vector database
    """
    conditions = []

    # Files in teams user belongs to
    for team_id in user_team_memberships:
        conditions.append({"acl.team_id": team_id})

    # Files where user is explicitly allowed
    for user_id in user_figma_ids:
        conditions.append({"acl.allowed_users": {"$contains": user_id}})

    return {"$or": conditions}
