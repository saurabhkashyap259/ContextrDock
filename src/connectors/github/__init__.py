"""GitHub connector plugin registration."""

from typing import Any

# Connector metadata
GITHUB_CONNECTOR_DEFINITION = {
    "connector_type": "github",
    "display_name": "GitHub",
    "description": "Sync repositories, issues, pull requests, and files from GitHub",
    "icon_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
    "category": "code",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": [
            "repo",  # Full access to repositories
            "read:org",  # Read organization membership
            "read:user",  # Read user profile
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "organization": {
                "type": "string",
                "title": "Organization",
                "description": "GitHub organization name (optional, syncs user repos if empty)",
            },
            "repositories": {
                "type": "array",
                "title": "Repositories",
                "description": "Specific repositories to sync (optional, syncs all if empty)",
                "items": {"type": "string"},
            },
        },
        "required": [],
    },
    "sync_config": {
        "default_schedule": "0 */3 * * *",  # Every 3 hours
        "supports_incremental": True,
        "cursor_state_schema": {
            "type": "object",
            "properties": {
                "last_updated": {"type": "string", "format": "date-time"},
                "synced_repos": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "rate_limits": {
        "requests_per_hour": 5000,
        "burst_size": 100,
    },
}


def get_connector_class():
    """Get the connector class for plugin loading.

    Returns:
        GitHubConnector class
    """
    from src.connectors.github.connector import GitHubConnector

    return GitHubConnector


def get_connector_definition() -> dict[str, Any]:
    """Get the connector definition for registration.

    Returns:
        Connector definition dict
    """
    return GITHUB_CONNECTOR_DEFINITION
