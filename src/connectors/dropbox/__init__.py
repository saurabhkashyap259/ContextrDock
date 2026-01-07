"""Dropbox connector plugin registration."""

from typing import Any, Dict

# Connector metadata
DROPBOX_CONNECTOR_DEFINITION = {
    "connector_type": "dropbox",
    "display_name": "Dropbox",
    "description": "Sync files, folders, and shared content from Dropbox",
    "icon_url": "https://cfl.dropboxstatic.com/static/images/logo_catalog/dropbox_webclip_152.png",
    "category": "storage",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "scopes": [
            "files.metadata.read",  # Read file metadata
            "files.content.read",  # Read file content
            "sharing.read",  # Read sharing information
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "folders": {
                "type": "array",
                "title": "Folders",
                "description": "Specific folders to sync (empty array = root)",
                "items": {"type": "string"},
                "default": [""],
            },
            "include_shared": {
                "type": "boolean",
                "title": "Include Shared Files",
                "description": "Include shared files and folders",
                "default": True,
            },
        },
        "required": [],
    },
    "sync_config": {
        "default_schedule": "0 */6 * * *",  # Every 6 hours
        "supports_incremental": True,
        "cursor_state_schema": {
            "type": "object",
            "properties": {
                "cursor": {"type": "string"},
            },
        },
    },
    "rate_limits": {
        "requests_per_minute": 200,
        "burst_size": 50,
    },
}


def get_connector_class():
    """Get the connector class for plugin loading.

    Returns:
        DropboxConnector class
    """
    from src.connectors.dropbox.connector import DropboxConnector

    return DropboxConnector


def get_connector_definition() -> Dict[str, Any]:
    """Get the connector definition for registration.

    Returns:
        Connector definition dict
    """
    return DROPBOX_CONNECTOR_DEFINITION
