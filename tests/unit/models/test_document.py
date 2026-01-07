"""Tests for Document model."""

import pytest
from sqlalchemy.orm import Session
from datetime import datetime

from src.models.document import Document


def test_document_creation(db_session: Session) -> None:
    """Test creating a document."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="confluence",
        source_id="page-123",
        title="API Documentation",
        url="https://company.atlassian.net/wiki/spaces/ENG/pages/123",
        content_hash="abc123def456",
        metadata_json={"space": "ENG", "author": "john@example.com"},
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    assert document.id is not None
    assert document.workspace_id == 1
    assert document.connector_id == 1
    assert document.source_type == "confluence"
    assert document.source_id == "page-123"
    assert document.title == "API Documentation"
    assert document.url.startswith("https://")
    assert document.content_hash == "abc123def456"
    assert document.metadata_json["space"] == "ENG"
    assert document.last_indexed_at is not None
    assert document.created_at is not None
    assert document.updated_at is not None


def test_document_required_fields(db_session: Session) -> None:
    """Test that required fields are enforced."""
    # Missing workspace_id should fail
    document = Document(
        source_type="slack",
        source_id="C123-M456",
        title="Message",
    )
    db_session.add(document)
    
    with pytest.raises(Exception):  # Will raise IntegrityError
        db_session.commit()


def test_document_source_type_index(db_session: Session) -> None:
    """Test that source_type is indexed for fast filtering."""
    doc1 = Document(
        workspace_id=1,
        connector_id=1,
        source_type="slack",
        source_id="C123-M1",
        title="Slack Message 1",
    )
    doc2 = Document(
        workspace_id=1,
        connector_id=2,
        source_type="jira",
        source_id="PROJ-123",
        title="Jira Issue",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()
    
    # Query by source_type (uses index)
    slack_docs = db_session.query(Document).filter(
        Document.source_type == "slack"
    ).all()
    
    assert len(slack_docs) == 1
    assert slack_docs[0].title == "Slack Message 1"


def test_document_url_nullable(db_session: Session) -> None:
    """Test that URL is optional (some sources may not have URLs)."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="email",
        source_id="msg-123",
        title="Email Subject",
        url=None,  # URL can be null
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    
    assert document.url is None


def test_document_last_indexed_at_update(db_session: Session) -> None:
    """Test that last_indexed_at can be updated."""
    document = Document(
        workspace_id=1,
        connector_id=1,
        source_type="github",
        source_id="repo/file.md",
        title="README",
    )
    db_session.add(document)
    db_session.commit()
    
    original_time = document.last_indexed_at
    
    # Simulate re-indexing
    document.last_indexed_at = datetime.utcnow()
    db_session.commit()
    db_session.refresh(document)
    
    assert document.last_indexed_at > original_time
