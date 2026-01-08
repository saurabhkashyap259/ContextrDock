"""ACL extraction and permission checking for Dropbox files."""

from typing import Any, Optional


def extract_folder_members(
    path: str,
    dropbox_client: Any,
) -> list[dict[str, Any]]:
    """Fetch members for a shared folder.

    Args:
        path: Folder path
        dropbox_client: DropboxConnector instance

    Returns:
        List of member dicts with email and access level
    """
    try:
        headers = dropbox_client._get_auth_headers()
        headers["Content-Type"] = "application/json"
        url = f"{dropbox_client.BASE_URL}/2/sharing/list_folder_members"

        # First get shared folder ID
        shared_folder_url = f"{dropbox_client.BASE_URL}/2/sharing/list_folders"
        response = dropbox_client._rate_limited_request(
            "POST", shared_folder_url, headers=headers, json={}
        )
        response.raise_for_status()

        folders = response.json().get("entries", [])
        shared_folder_id = None
        for folder in folders:
            if folder.get("path_lower") == path.lower():
                shared_folder_id = folder.get("shared_folder_id")
                break

        if not shared_folder_id:
            return []

        # Get folder members
        data = {"shared_folder_id": shared_folder_id}
        response = dropbox_client._rate_limited_request(
            "POST", url, headers=headers, json=data
        )
        response.raise_for_status()

        result = response.json()
        members = []

        # Extract user members
        for user in result.get("users", []):
            members.append({
                "email": user.get("user", {}).get("email"),
                "access_level": user.get("access_type", {}).get(".tag"),
            })

        return members
    except Exception:
        # If we can't fetch members, return empty list
        return []


def normalize_dropbox_acl(
    path: str,
    is_shared: bool,
    members: Optional[list[dict[str, Any]]] = None,
    shared_links: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Normalize Dropbox ACL to standard format.

    Args:
        path: File or folder path
        is_shared: Whether file/folder is shared
        members: List of member dicts with email and access_level
        shared_links: List of shared link dicts

    Returns:
        Normalized ACL dict with access_level and allowed_users
    """
    if members is None:
        members = []
    if shared_links is None:
        shared_links = []

    # Check if public via shared link
    has_public_link = any(
        link.get(".tag") == "file" and not link.get("link_permissions", {}).get("require_password")
        for link in shared_links
    )

    if has_public_link:
        return {
            "access_level": "public_link",
            "path": path,
            "shared_link": shared_links[0].get("url"),
        }

    if not is_shared:
        # Personal file
        return {
            "access_level": "personal",
            "path": path,
        }

    # Shared with specific users
    allowed_users = []
    for member in members:
        email = member.get("email")
        access_level = member.get("access_level")

        # Include members with viewer, editor, or owner access
        if access_level in ["viewer", "editor", "owner"]:
            if email:
                allowed_users.append(email)

    return {
        "access_level": "shared",
        "path": path,
        "allowed_users": allowed_users,
    }


def check_user_access(
    user_email: str,
    acl_metadata: dict[str, Any],
) -> bool:
    """Check if user has access to a Dropbox document.

    Args:
        user_email: User's email address
        acl_metadata: ACL metadata from document

    Returns:
        True if user has access, False otherwise
    """
    access_level = acl_metadata.get("access_level")

    # Public links are accessible to anyone
    if access_level == "public_link":
        return True

    # Personal files require owner match
    if access_level == "personal":
        owner_email = acl_metadata.get("owner_email")
        return user_email == owner_email

    # Shared files require explicit access
    if access_level == "shared":
        allowed_users = acl_metadata.get("allowed_users", [])
        return user_email in allowed_users

    # Default deny
    return False


def build_acl_filter_query(
    user_email: str,
) -> dict[str, Any]:
    """Build vector database filter query for Dropbox ACL.

    Args:
        user_email: User's email address

    Returns:
        Filter query dict for vector database
    """
    conditions = []

    # Public links
    conditions.append({"acl.access_level": "public_link"})

    # Personal files owned by user
    conditions.append({
        "acl.access_level": "personal",
        "acl.owner_email": user_email,
    })

    # Shared files where user is allowed
    conditions.append({
        "acl.access_level": "shared",
        "acl.allowed_users": {"$contains": user_email},
    })

    return {"$or": conditions}
