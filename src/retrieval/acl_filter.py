"""Permission-aware filtering using ACLs (fail-closed behavior)."""

from typing import Any


def filter_by_permissions(
    results: list[dict[str, Any]],
    user_identities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter search results based on user permissions (fail-closed).

    Implements fail-closed security: chunks without valid ACLs are excluded.

    ACL formats supported:
    - Email-based: {"readers": ["user@example.com"]}
    - External ID: {"readers": ["U12345", "accountId123"]}
    - Channel-based: {"channel": "C123"}
    - Public: {"public": True}

    Args:
        results: Search results with ACL metadata
        user_identities: User's connector identities with email/external_id/channels

    Returns:
        Filtered results containing only permitted chunks

    Security:
        - Empty/null/missing ACL → DENY (fail-closed)
        - Empty user_identities → DENY all
        - Match on email, external_id, channel membership, or public flag

    Example:
        >>> user_identities = [
        ...     {"connector_type": "slack", "email": "user@example.com",
        ...      "external_id": "U12345", "channels": ["C123"]}
        ... ]
        >>> results = [
        ...     {"chunk_id": 1, "acl": {"readers": ["user@example.com"]}},
        ...     {"chunk_id": 2, "acl": {"channel": "C123"}},
        ...     {"chunk_id": 3, "acl": {"readers": ["other@example.com"]}},
        ... ]
        >>> filtered = filter_by_permissions(results, user_identities)
        >>> len(filtered)
        2
    """
    if not user_identities:
        # Fail-closed: no identities means no access
        return []

    # Extract all user identifiers for matching
    user_emails = set()
    user_external_ids = set()
    user_channels = set()

    for identity in user_identities:
        if "email" in identity:
            user_emails.add(identity["email"])
        if "external_id" in identity:
            user_external_ids.add(identity["external_id"])
        if "channels" in identity:
            user_channels.update(identity["channels"])

    filtered_results = []

    for result in results:
        acl = result.get("acl")

        # Fail-closed: no ACL means deny
        if not acl or not isinstance(acl, dict):
            continue

        # Check if public
        if acl.get("public") is True:
            filtered_results.append(result)
            continue

        # Check email/external_id in readers list
        readers = acl.get("readers", [])
        if isinstance(readers, list):
            for reader in readers:
                if reader in user_emails or reader in user_external_ids:
                    filtered_results.append(result)
                    break
            else:
                # No match in readers, check channel membership
                channel = acl.get("channel")
                if channel and channel in user_channels:
                    filtered_results.append(result)
        else:
            # readers is not a list, check channel
            channel = acl.get("channel")
            if channel and channel in user_channels:
                filtered_results.append(result)

    return filtered_results
