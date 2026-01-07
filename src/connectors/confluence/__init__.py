"""Confluence connector package.

Exports ConfluenceConnector and connector definition for plugin discovery.
"""

from src.connectors.confluence.connector import ConfluenceConnector

# Confluence connector definition
CONFLUENCE_CONNECTOR_DEFINITION = {
    "name": "confluence",
    "display_name": "Confluence",
    "description": "Connect to Confluence Cloud to index pages, blog posts, and spaces",
    "icon_url": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/confluence.svg",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": [
            "read:confluence-content.all",
            "read:confluence-space.summary",
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "instance_url": {
                "type": "string",
                "format": "uri",
                "title": "Confluence Instance URL",
                "description": "Your Confluence Cloud instance URL (e.g., https://yourcompany.atlassian.net)",
                "examples": ["https://mycompany.atlassian.net"],
            },
            "space_keys": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Space Keys",
                "description": "List of space keys to sync (leave empty for all spaces)",
                "examples": [["ENG", "DOCS", "PRODUCT"]],
            },
        },
        "required": ["instance_url"],
    },
    "sync_schedule_options": ["hourly", "6-hourly", "daily"],
    "default_sync_schedule": "6-hourly",
    "supports_incremental_sync": True,
    "rate_limit": {
        "calls": 10,
        "period": 1,  # seconds
        "description": "Confluence Cloud rate limit: 10 requests per second",
    },
}


def get_connector_class():
    """Get ConfluenceConnector class for plugin discovery."""
    return ConfluenceConnector


def get_connector_definition() -> dict:
    """Get connector definition for registration."""
    return CONFLUENCE_CONNECTOR_DEFINITION


__all__ = [
    "ConfluenceConnector",
    "CONFLUENCE_CONNECTOR_DEFINITION",
    "get_connector_class",
    "get_connector_definition",
]
