"""Slack connector package.

Exports SlackConnector and connector definition for plugin discovery.
"""

from src.connectors.slack.connector import SlackConnector

# Slack connector definition
SLACK_CONNECTOR_DEFINITION = {
    "name": "slack",
    "display_name": "Slack",
    "description": "Connect to Slack workspaces to index channels, messages, and threads",
    "icon_url": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/slack.svg",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": [
            "channels:read",
            "channels:history",
            "groups:read",
            "groups:history",
            "users:read",
            "users:read.email",
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "workspace_url": {
                "type": "string",
                "format": "uri",
                "title": "Workspace URL",
                "description": "Your Slack workspace URL (e.g., mycompany.slack.com)",
                "examples": ["mycompany.slack.com"],
            },
        },
        "required": ["workspace_url"],
    },
    "sync_schedule_options": ["hourly", "6-hourly", "daily"],
    "default_sync_schedule": "hourly",
    "supports_incremental_sync": True,
    "rate_limit": {
        "calls": 50,
        "period": 60,  # seconds
        "description": "Slack Tier 3 rate limit: 50+ calls per minute",
    },
}


def get_connector_class():
    """Get SlackConnector class for plugin discovery."""
    return SlackConnector


def get_connector_definition() -> dict:
    """Get connector definition for registration."""
    return SLACK_CONNECTOR_DEFINITION


__all__ = [
    "SlackConnector",
    "SLACK_CONNECTOR_DEFINITION",
    "get_connector_class",
    "get_connector_definition",
]
