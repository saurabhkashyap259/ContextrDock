"""Pytest configuration and shared fixtures for ContextDock tests."""

from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

# Note: Base will be imported from src.models.base once created


@pytest.fixture(scope="session")
def db_engine() -> Generator:
    """Create a test database engine (synchronous)."""
    engine = create_engine(
        "postgresql://contextdock:password@localhost:5432/contextdock_test",
        echo=False,
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def async_db_engine() -> AsyncGenerator:
    """Create a test database engine (asynchronous)."""
    engine = create_async_engine(
        "postgresql+asyncpg://contextdock:password@localhost:5432/contextdock_test",
        echo=False,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: any) -> Generator[Session, None, None]:
    """Create a new database session for a test."""
    SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
async def async_db_session(
    async_db_engine: any,
) -> AsyncGenerator[AsyncSession, None]:
    """Create a new async database session for a test."""
    SessionLocal = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def test_user() -> dict:
    """Create a test user with known properties."""
    return {
        "id": 1,
        "email": "test@example.com",
        "role": "user",
        "connector_identities": {
            "slack": "U123456",
            "jira": "account-id-123",
            "confluence": "account-id-123",
            "github": "testuser",
        },
    }


@pytest.fixture
def test_admin_user() -> dict:
    """Create a test admin user."""
    return {
        "id": 2,
        "email": "admin@example.com",
        "role": "admin",
        "connector_identities": {},
    }


@pytest.fixture
def mock_connector() -> MagicMock:
    """Create a mock connector for testing."""
    connector = MagicMock()
    connector.id = 1
    connector.type = "confluence"
    connector.status = "active"
    connector.config_json = {
        "space_keys": ["ENG", "PRODUCT"],
    }
    connector.last_sync_at = None
    return connector


@pytest.fixture
def mock_document() -> dict:
    """Create a mock document for testing."""
    return {
        "id": 1,
        "source_type": "confluence",
        "source_id": "page-123",
        "title": "API Authentication Strategy",
        "url": "https://example.atlassian.net/wiki/spaces/ENG/pages/123",
        "content": "We use OAuth 2.0 for API authentication...",
        "content_hash": "abc123",
        "metadata_json": {
            "space": "ENG",
            "author": "john@example.com",
        },
    }


@pytest.fixture
def mock_document_chunk() -> dict:
    """Create a mock document chunk for testing."""
    return {
        "id": 1,
        "document_id": 1,
        "content": "We use OAuth 2.0 for API authentication with JWT tokens.",
        "token_count": 15,
        "embedding_id": "emb-123",
        "acl_json": {
            "allowed_user_ids": [1, 2, 3],
        },
        "chunk_index": 0,
    }
