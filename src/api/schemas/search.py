"""Pydantic schemas for search API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request schema."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language search query",
        examples=["user engagement ideas", "ContextDock implementation"],
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip for pagination",
    )
    channel_id: Optional[str] = Field(
        default=None,
        description="Filter results by Slack channel ID",
    )
    source_type: Optional[str] = Field(
        default=None,
        description="Filter by source type (slack, confluence, jira, etc.)",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score threshold",
    )


class SearchResultMetadata(BaseModel):
    """Metadata for a search result."""

    source_type: str = Field(description="Type of source (slack, confluence, etc.)")
    source_id: str = Field(description="External ID in source system")
    channel_id: Optional[str] = Field(default=None, description="Channel ID (for Slack)")
    channel_name: Optional[str] = Field(default=None, description="Channel name (for Slack)")
    user_id: Optional[str] = Field(default=None, description="User ID")
    username: Optional[str] = Field(default=None, description="Username or display name")
    message_ts: Optional[str] = Field(default=None, description="Message timestamp (Slack)")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")


class SearchResult(BaseModel):
    """Individual search result."""

    id: int = Field(description="Document ID")
    title: str = Field(description="Document title or first line")
    content: str = Field(description="Document content or excerpt")
    url: Optional[str] = Field(default=None, description="URL to original document")
    score: float = Field(description="Relevance score (0.0-1.0)", ge=0.0, le=1.0)
    metadata: SearchResultMetadata = Field(description="Additional metadata")


class SearchResponse(BaseModel):
    """Search response schema."""

    query: str = Field(description="Original search query")
    total: int = Field(description="Total number of results", ge=0)
    limit: int = Field(description="Maximum results returned", ge=1)
    offset: int = Field(description="Results offset for pagination", ge=0)
    results: List[SearchResult] = Field(description="Search results")
    took_ms: float = Field(description="Query execution time in milliseconds", ge=0)


class SearchStatsResponse(BaseModel):
    """Search index statistics."""

    total_documents: int = Field(description="Total documents indexed", ge=0)
    total_chunks: int = Field(description="Total document chunks", ge=0)
    vector_dimensions: int = Field(description="Embedding vector dimensions", ge=0)
    sources: dict = Field(description="Document count by source type")
    last_indexed: Optional[datetime] = Field(
        default=None,
        description="Timestamp of most recent indexing",
    )
