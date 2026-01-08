"""Identity resolution service for mapping users to connector-specific identities."""

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.models.user import User
from src.services.cache import get_redis_client

# Cache TTL: 1 hour (3600 seconds) - T205
IDENTITY_CACHE_TTL = 3600


def resolve_user_identities(
    db_session: Session,
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    workspace_id: Optional[int] = None,
    use_cache: bool = True,
) -> Optional[list[dict[str, Any]]]:
    """
    Resolve user's connector identities for permission checking.

    Maps a user (by ID or email) to their connector-specific identities
    (e.g., Slack user ID, Jira account ID, GitHub username).

    This enables ACL filtering by matching document permissions against
    the user's various connector identities.

    With caching enabled (T205), identities are cached in Redis for 1 hour
    to reduce database load. Cache key format: "identity:{user_id}:{workspace_id}"

    Args:
        db_session: Database session
        user_id: User ID (primary lookup method)
        email: User email (alternative lookup, requires workspace_id)
        workspace_id: Workspace ID (required when using email lookup)
        use_cache: Whether to use Redis caching (default: True)

    Returns:
        List of identity dicts with connector_type, external_id, email, and
        connector-specific fields (channels, organizations, etc.).
        Returns None if user not found.

    Raises:
        ValueError: If neither user_id nor (email + workspace_id) provided

    Example:
        >>> identities = resolve_user_identities(session, user_id=1)
        >>> identities
        [
            {
                "connector_type": "slack",
                "external_id": "U12345",
                "email": "user@example.com",
                "channels": ["C123", "C456"]
            },
            {
                "connector_type": "jira",
                "external_id": "accountId123",
                "email": "user@example.com"
            }
        ]
    """
    # Validate input
    if user_id is None and (email is None or workspace_id is None):
        raise ValueError("Either user_id or both email and workspace_id must be provided")

    # Try cache first if enabled
    if use_cache and user_id is not None and workspace_id is not None:
        cache_key = f"identity:{user_id}:{workspace_id}"
        try:
            redis_client = get_redis_client()
            cached_data = redis_client.get(cache_key)
            if cached_data:
                # Cache hit
                return json.loads(cached_data)
        except Exception as e:
            # Cache failure should not break the request
            # Log and continue to database
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to read from identity cache: {e}")

    # Fetch user from database
    if user_id is not None:
        user = db_session.query(User).filter(User.id == user_id).first()
    else:
        user = db_session.query(User).filter(
            User.email == email,
            User.workspace_id == workspace_id,
        ).first()

    if not user:
        return None

    # Extract connector identities
    connector_identities = user.connector_identities

    if not connector_identities or not isinstance(connector_identities, dict):
        identities = []
    else:
        # Build identity list
        identities = []

        for connector_type, identity_data in connector_identities.items():
            if not isinstance(identity_data, dict):
                continue

            # Create identity dict with connector_type
            identity = {"connector_type": connector_type}

            # Copy all fields from identity_data
            identity.update(identity_data)

            identities.append(identity)

    # Cache the result if caching is enabled
    if use_cache and user_id is not None and workspace_id is not None:
        cache_key = f"identity:{user_id}:{workspace_id}"
        try:
            redis_client = get_redis_client()
            redis_client.setex(
                cache_key,
                IDENTITY_CACHE_TTL,
                json.dumps(identities)
            )
        except Exception as e:
            # Cache write failure should not break the request
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to write to identity cache: {e}")

    return identities
