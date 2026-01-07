"""Tests for ConnectorDefinition model."""

import pytest
from sqlalchemy.orm import Session

from src.models.connector_definition import ConnectorDefinition


def test_connector_definition_creation(db_session: Session) -> None:
    """Test creating a connector definition."""
    definition = ConnectorDefinition(
        name="Slack",
        connector_type="slack",
        config_schema={
            "type": "object",
            "properties": {
                "workspace_url": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["workspace_url"],
        },
        oauth_scopes=["channels:read", "channels:history", "users:read"],
        supports_read=True,
        supports_write=False,
    )
    db_session.add(definition)
    db_session.commit()
    db_session.refresh(definition)

    assert definition.id is not None
    assert definition.name == "Slack"
    assert definition.connector_type == "slack"
    assert definition.supports_read is True
    assert definition.supports_write is False
    assert "channels:read" in definition.oauth_scopes


def test_connector_definition_unique_type(db_session: Session) -> None:
    """Test that connector_type must be unique."""
    definition1 = ConnectorDefinition(
        name="Slack",
        connector_type="slack",
        config_schema={},
        oauth_scopes=["channels:read"],
    )
    db_session.add(definition1)
    db_session.commit()
    
    definition2 = ConnectorDefinition(
        name="Slack 2",
        connector_type="slack",  # Duplicate type
        config_schema={},
        oauth_scopes=["channels:read"],
    )
    db_session.add(definition2)
    
    with pytest.raises(Exception):  # Will raise IntegrityError
        db_session.commit()


def test_connector_definition_version(db_session: Session) -> None:
    """Test connector definition versioning."""
    definition = ConnectorDefinition(
        name="Jira",
        connector_type="jira",
        config_schema={},
        oauth_scopes=["read:jira-work"],
        version="1.0.0",
    )
    db_session.add(definition)
    db_session.commit()
    db_session.refresh(definition)
    
    assert definition.version == "1.0.0"
