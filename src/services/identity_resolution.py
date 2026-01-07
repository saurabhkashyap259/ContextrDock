"""Identity resolution service for mapping users to connector-specific identities."""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.user import User


def resolve_user_identities(
    db_session: Session,
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    workspace_id: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Resolve user's connector identities for permission checking.
    
    Maps a user (by ID or email) to their connector-specific identities
    (e.g., Slack user ID, Jira account ID, GitHub username).
    
    This enables ACL filtering by matching document permissions against
    the user's various connector identities.
    
    Args:
        db_session: Database session
        user_id: User ID (primary lookup method)
        email: User email (alternative lookup, requires workspace_id)
        workspace_id: Workspace ID (required when using email lookup)
        
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
    
    # Fetch user
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
        return []
    
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
    
    return identities
