"""Document ingestion pipeline: chunk → embed → store."""

import hashlib
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from src.ingestion.chunker import chunk_text
from src.ingestion.embeddings import EmbeddingService, get_token_count
from src.integrations.vector_db import QdrantClient
from src.models.document import Document
from src.models.document_chunk import DocumentChunk


def compute_content_hash(content: str) -> str:
    """
    Compute SHA256 hash of content for change detection.
    
    Args:
        content: Document content
        
    Returns:
        Hex string of hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_document(
    db_session: Session,
    workspace_id: int,
    connector_id: Optional[int],
    source_type: str,
    source_id: str,
    title: str,
    content: str,
    url: Optional[str] = None,
    acl: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> Document:
    """
    Ingest a document into the system.
    
    Process:
    1. Create/update Document record in PostgreSQL
    2. Chunk the content
    3. Generate embeddings for each chunk
    4. Store chunks in PostgreSQL with ACL
    5. Store vectors in Qdrant with metadata
    
    Args:
        db_session: Database session
        workspace_id: Workspace ID
        connector_id: Connector ID (or None for manual uploads)
        source_type: Source system ("confluence", "slack", "jira", etc.)
        source_id: External document ID
        title: Document title
        content: Full document content
        url: Deep link to original document
        acl: Access control list
        metadata: Additional metadata
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        
    Returns:
        Created/updated Document instance
        
    Example:
        >>> document = ingest_document(
        ...     db_session=session,
        ...     workspace_id=1,
        ...     connector_id=5,
        ...     source_type="confluence",
        ...     source_id="page-123",
        ...     title="API Documentation",
        ...     content="Our API uses OAuth 2.0...",
        ...     url="https://company.atlassian.net/wiki/123",
        ...     acl={"readers": ["eng-team@company.com"]},
        ... )
    """
    acl = acl or {}
    metadata = metadata or {}
    
    # Compute content hash for change detection
    content_hash = compute_content_hash(content)
    
    # Create or update document
    document = Document(
        workspace_id=workspace_id,
        connector_id=connector_id,
        source_type=source_type,
        source_id=source_id,
        title=title,
        url=url,
        content_hash=content_hash,
        metadata_json=metadata,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    
    # If no content, return early
    if not content or not content.strip():
        return document
    
    # Step 1: Chunk the content
    chunks = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    if not chunks:
        return document
    
    # Step 2: Generate embeddings for all chunks
    embedding_service = EmbeddingService()
    embeddings = embedding_service.embed_texts(chunks)
    
    # Step 3: Initialize Qdrant client
    qdrant_client = QdrantClient()
    qdrant_client.ensure_collection(vector_size=len(embeddings[0]))
    
    # Step 4: Store chunks in PostgreSQL and vectors in Qdrant
    for idx, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
        # Generate unique ID for this chunk
        embedding_id = str(uuid4())
        
        # Calculate token count
        token_count = get_token_count(chunk_content)
        
        # Create DocumentChunk record
        chunk_record = DocumentChunk(
            document_id=document.id,
            chunk_index=idx,
            content=chunk_content,
            token_count=token_count,
            embedding_id=embedding_id,
            acl_json=acl,
        )
        db_session.add(chunk_record)
        
        # Prepare metadata for Qdrant
        vector_metadata = {
            "workspace_id": workspace_id,
            "document_id": document.id,
            "chunk_id": chunk_record.id,
            "source_type": source_type,
            "source_id": source_id,
            "title": title,
            "url": url,
            "chunk_index": idx,
            **acl,  # Include ACL in vector metadata for filtering
        }
        
        # Store vector in Qdrant
        qdrant_client.upsert_vector(
            vector_id=embedding_id,
            embedding=embedding,
            metadata=vector_metadata,
        )
    
    db_session.commit()
    
    return document
