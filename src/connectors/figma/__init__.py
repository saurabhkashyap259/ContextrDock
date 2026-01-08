"""Figma connector plugin registration."""

from typing import Any

# Connector metadata
FIGMA_CONNECTOR_DEFINITION = {
    "connector_type": "figma",
    "display_name": "Figma",
    "description": "Sync design files, comments, and versions from Figma",
    "icon_url": "https://cdn.sanity.io/images/599r6htc/localized/46a76c802176eb17b04e12108de7e7e0f3736dc6-1024x1024.png",
    "category": "design",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://www.figma.com/oauth",
        "token_url": "https://www.figma.com/api/oauth/token",
        "scopes": [
            "files:read",  # Read file content
            "file_comments:read",  # Read comments
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "team_id": {
                "type": "string",
                "title": "Team ID",
                "description": "Figma team ID (required)",
            },
            "project_ids": {
                "type": "array",
                "title": "Project IDs",
                "description": "Specific projects to sync (optional, syncs all if empty)",
                "items": {"type": "string"},
            },
        },
        "required": ["team_id"],
    },
    "sync_config": {
        "default_schedule": "0 */6 * * *",  # Every 6 hours
        "supports_incremental": True,
        "cursor_state_schema": {
            "type": "object",
            "properties": {
                "last_updated": {"type": "string", "format": "date-time"},
                "synced_files": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "rate_limits": {
        "requests_per_minute": 100,
        "burst_size": 20,
    },
}


def get_connector_class():
    """Get the connector class for plugin loading.

    Returns:
        FigmaConnector class
    """
    from src.connectors.figma.connector import FigmaConnector

    return FigmaConnector


def get_connector_definition() -> dict[str, Any]:
    """Get the connector definition for registration.

    Returns:
        Connector definition dict
    """
    return FIGMA_CONNECTOR_DEFINITION
