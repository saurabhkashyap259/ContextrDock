"""Slack ACL extraction utilities.

Extracts access control metadata from Slack documents for permission-aware retrieval.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def extract_channel_members(channel_id: str, slack_client: Any) -> list[str]:
    """Fetch member list for a Slack channel.

    Args:
        channel_id: Slack channel ID
        slack_client: Authenticated Slack client

    Returns:
        List of user IDs who are members of the channel
    """
    try:
        response = slack_client.conversations_members(channel=channel_id)
        if response.get("ok"):
            return response.get("members", [])
    except Exception as e:
        logger.warning(f"Failed to fetch members for channel {channel_id}: {e}")

    return []


def normalize_slack_acl(
    channel_type: str,
    channel_id: str,
    workspace_id: str,
    allowed_users: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Normalize Slack ACL metadata to standard format.

    Args:
        channel_type: Type of channel (public, private, dm)
        channel_id: Slack channel ID
        workspace_id: Slack workspace ID
        allowed_users: List of user IDs with access (for private channels/DMs)

    Returns:
        Normalized ACL metadata dict
    """
    acl = {
        "connector_type": "slack",
        "workspace_id": workspace_id,
        "channel_id": channel_id,
        "channel_type": channel_type,
    }

    if channel_type == "public":
        # Public channels - accessible to all workspace members
        acl["access_level"] = "workspace"
        acl["requires_membership"] = False
    elif channel_type == "private":
        # Private channels - only specific members
        acl["access_level"] = "restricted"
        acl["requires_membership"] = True
        acl["allowed_users"] = allowed_users or []
    elif channel_type == "dm":
        # Direct messages - only participants
        acl["access_level"] = "direct"
        acl["requires_membership"] = True
        acl["allowed_users"] = allowed_users or []

    return acl


def check_user_access(
    user_slack_id: str,
    acl_metadata: dict[str, Any],
    user_workspace_membership: set[str],
) -> bool:
    """Check if user has access to a Slack document.

    Args:
        user_slack_id: User's Slack ID in this workspace
        acl_metadata: ACL metadata from document
        user_workspace_membership: Set of workspace IDs user is member of

    Returns:
        True if user has access, False otherwise
    """
    workspace_id = acl_metadata.get("workspace_id")
    channel_type = acl_metadata.get("channel_type")

    # Check workspace membership
    if workspace_id not in user_workspace_membership:
        return False

    # Public channels - accessible to all workspace members
    if channel_type == "public":
        return True

    # Private channels and DMs - check explicit user list
    allowed_users = acl_metadata.get("allowed_users", [])
    return user_slack_id in allowed_users


def build_acl_filter_query(
    user_slack_ids: dict[str, str],  # workspace_id -> user_slack_id
    workspace_ids: set[str],
) -> dict[str, Any]:
    """Build vector database filter for Slack ACL enforcement.

    Args:
        user_slack_ids: Mapping of workspace_id to user's Slack ID in that workspace
        workspace_ids: Set of workspace IDs user is member of

    Returns:
        Filter query dict for vector database
    """
    # Build filter conditions:
    # 1. Public channels in user's workspaces
    # 2. Private channels/DMs where user is in allowed_users list

    conditions = []

    for workspace_id in workspace_ids:
        # Public channels in this workspace
        conditions.append({
            "workspace_id": workspace_id,
            "channel_type": "public",
        })

        # Private channels/DMs where user is member
        user_slack_id = user_slack_ids.get(workspace_id)
        if user_slack_id:
            conditions.append({
                "workspace_id": workspace_id,
                "channel_type": {"$in": ["private", "dm"]},
                "allowed_users": {"$contains": user_slack_id},
            })

    # Combine with OR logic
    return {"$or": conditions} if len(conditions) > 1 else conditions[0]
