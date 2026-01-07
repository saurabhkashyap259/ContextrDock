"""Jira connector package.

Exports JiraConnector and connector definition for plugin discovery.
"""

from src.connectors.jira.connector import JiraConnector

# Jira connector definition
JIRA_CONNECTOR_DEFINITION = {
    "name": "jira",
    "display_name": "Jira",
    "description": "Connect to Jira Cloud to index issues, comments, and project metadata",
    "icon_url": "https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/jira.svg",
    "auth_type": "oauth2",
    "oauth_config": {
        "authorization_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": [
            "read:jira-work",
            "read:jira-user",
        ],
    },
    "config_schema": {
        "type": "object",
        "properties": {
            "instance_url": {
                "type": "string",
                "format": "uri",
                "title": "Jira Instance URL",
                "description": "Your Jira Cloud instance URL (e.g., https://yourcompany.atlassian.net)",
                "examples": ["https://mycompany.atlassian.net"],
            },
            "project_keys": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Project Keys",
                "description": "List of project keys to sync (leave empty for all projects)",
                "examples": [["PROJ", "DEV", "SUPPORT"]],
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
        "description": "Jira Cloud rate limit: 10 requests per second",
    },
}


def get_connector_class():
    """Get JiraConnector class for plugin discovery."""
    return JiraConnector


def get_connector_definition() -> dict:
    """Get connector definition for registration."""
    return JIRA_CONNECTOR_DEFINITION


__all__ = [
    "JiraConnector",
    "JIRA_CONNECTOR_DEFINITION",
    "get_connector_class",
    "get_connector_definition",
]
