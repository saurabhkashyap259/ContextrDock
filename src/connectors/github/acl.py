"""ACL extraction and permission checking for GitHub repositories."""

from typing import Any, Dict, List, Optional, Set


def extract_repo_collaborators(
    owner: str,
    repo: str,
    github_client: Any,
) -> List[Dict[str, Any]]:
    """Fetch collaborators for a repository.

    Args:
        owner: Repository owner
        repo: Repository name
        github_client: GitHubConnector instance

    Returns:
        List of collaborator dicts with login and permissions
    """
    try:
        headers = github_client._get_auth_headers()
        url = f"{github_client.BASE_URL}/repos/{owner}/{repo}/collaborators"

        response = github_client._rate_limited_request(
            "GET", url, headers=headers, params={"per_page": 100}
        )
        response.raise_for_status()

        collaborators = response.json()
        return [
            {
                "login": collab["login"],
                "permissions": collab.get("permissions", {}),
            }
            for collab in collaborators
        ]
    except Exception:
        # If we can't fetch collaborators, return empty list
        return []


def normalize_github_acl(
    visibility: str,
    owner: str,
    repo_name: str,
    collaborators: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Normalize GitHub ACL to standard format.

    Args:
        visibility: Repository visibility (public, private, internal)
        owner: Repository owner
        repo_name: Repository name
        collaborators: List of collaborator dicts with login and permissions

    Returns:
        Normalized ACL dict with access_level and allowed_users
    """
    if collaborators is None:
        collaborators = []

    if visibility == "public":
        return {
            "access_level": "public",
            "owner": owner,
            "repo_name": repo_name,
        }

    # Private or internal repository
    allowed_users = []
    for collab in collaborators:
        # Include collaborators with read, write, or admin permissions
        permissions = collab.get("permissions", {})
        if (
            permissions.get("pull")  # read
            or permissions.get("push")  # write
            or permissions.get("admin")
        ):
            allowed_users.append(collab["login"])

    return {
        "access_level": "private",
        "owner": owner,
        "repo_name": repo_name,
        "allowed_users": allowed_users,
    }


def check_user_access(
    user_github_login: str,
    acl_metadata: Dict[str, Any],
    user_org_memberships: Set[str],
) -> bool:
    """Check if user has access to a GitHub document.

    Args:
        user_github_login: User's GitHub login
        acl_metadata: ACL metadata from document
        user_org_memberships: Set of organization names user belongs to

    Returns:
        True if user has access, False otherwise
    """
    access_level = acl_metadata.get("access_level")

    # Public repositories are accessible to everyone
    if access_level == "public":
        return True

    # Private repositories require explicit access
    if access_level == "private":
        allowed_users = acl_metadata.get("allowed_users", [])

        # Check if user is in allowed list
        if user_github_login in allowed_users:
            return True

        # Check if user is member of owner organization
        owner = acl_metadata.get("owner")
        if owner in user_org_memberships:
            return True

        return False

    # Internal repositories require organization membership
    if access_level == "internal":
        owner = acl_metadata.get("owner")
        return owner in user_org_memberships

    # Default deny
    return False


def build_acl_filter_query(
    user_github_logins: List[str],
    user_org_memberships: Set[str],
) -> Dict[str, Any]:
    """Build vector database filter query for GitHub ACL.

    Args:
        user_github_logins: List of user's GitHub logins (may have multiple)
        user_org_memberships: Set of organization names user belongs to

    Returns:
        Filter query dict for vector database
    """
    conditions = []

    # Public repositories
    conditions.append({"acl.access_level": "public"})

    # Private repositories where user is allowed
    for login in user_github_logins:
        conditions.append({"acl.allowed_users": {"$contains": login}})

    # Repositories owned by user's organizations
    for org in user_org_memberships:
        conditions.append({"acl.owner": org})

    return {"$or": conditions}
