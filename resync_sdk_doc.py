#!/usr/bin/env python3
"""Re-sync the SDK Documentation page with proper chunking."""

import logging
import sys
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from src.config.settings import Settings
from src.database import SessionLocal
from src.models.document import Document
from src.models.document_chunk import DocumentChunk

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = Settings()
openai_client = OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url)

EMBEDDING_MODEL = "text-embedding-3-small"
MAX_CHUNK_SIZE = 1000  # tokens (roughly 750 words)


def chunk_text(text: str, max_tokens: int = MAX_CHUNK_SIZE) -> List[str]:
    """Split text into chunks."""
    # Simple chunking by characters (rough token estimation: 1 token ≈ 4 chars)
    max_chars = max_tokens * 4
    chunks = []
    
    # Try splitting by double newlines first
    paragraphs = text.split('\n\n')
    
    # If that doesn't help (all in one paragraph), try sentences
    if len(paragraphs) == 1 or all(len(p) > max_chars for p in paragraphs):
        # Split by sentences (. followed by space or newline)
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        paragraphs = sentences
    
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_size = len(para)
        
        # If single paragraph is too large, force split it
        if para_size > max_chars:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            # Split large paragraph into smaller pieces
            words = para.split()
            temp_chunk = []
            temp_size = 0
            
            for word in words:
                word_size = len(word) + 1  # +1 for space
                if temp_size + word_size > max_chars and temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                    temp_chunk = [word]
                    temp_size = word_size
                else:
                    temp_chunk.append(word)
                    temp_size += word_size
            
            if temp_chunk:
                chunks.append(' '.join(temp_chunk))
            continue
        
        if current_size + para_size > max_chars and current_chunk:
            # Save current chunk
            chunks.append(' '.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
    
    # Add remaining
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    logger.info(f"Chunk sizes: {[len(c) for c in chunks]}")
    return chunks


def generate_embedding(text: str) -> List[float]:
    """Generate embedding."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text[:8000]  # Truncate if needed
    )
    return response.data[0].embedding


def resync_sdk_doc():
    """Re-sync the SDK Documentation page."""
    db = SessionLocal()
    
    try:
        # Get the document
        doc = db.query(Document).filter_by(source_id='confluence_4882565').first()
        
        if not doc:
            logger.error("Document not found!")
            return
        
        logger.info(f"Found document: {doc.title}")
        
        # Fetch content from Confluence
        import requests
        import base64
        import os
        import re
        
        email = os.getenv('CONFLUENCE_EMAIL')
        token = os.getenv('CONFLUENCE_API_TOKEN')
        instance_url = os.getenv('CONFLUENCE_INSTANCE_URL')
        
        auth_string = f'{email}:{token}'
        auth_bytes = auth_string.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_string = base64_bytes.decode('ascii')
        
        headers = {
            'Authorization': f'Basic {base64_string}',
            'Accept': 'application/json'
        }
        
        url = f'{instance_url}/wiki/api/v2/pages/4882565?body-format=storage'
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch page: {response.status_code}")
            return
        
        page_data = response.json()
        content_html = page_data.get('body', {}).get('storage', {}).get('value', '')
        
        # Strip HTML
        content_text = re.sub(r'<[^>]+>', '', content_html)
        content_text = re.sub(r'\s+', ' ', content_text).strip()
        
        logger.info(f"Content length: {len(content_text)} characters")
        
        # Delete existing chunks
        db.query(DocumentChunk).filter_by(document_id=doc.id).delete()
        db.commit()
        logger.info("Deleted old chunks")
        
        # Chunk the content
        chunks = chunk_text(content_text, max_tokens=1000)
        logger.info(f"Created {len(chunks)} chunks")
        
        # Process each chunk
        for idx, chunk_content in enumerate(chunks):
            logger.info(f"Processing chunk {idx+1}/{len(chunks)}")
            
            # Generate embedding
            embedding_vector = generate_embedding(chunk_content)
            
            # Create chunk record
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_content,
                token_count=len(chunk_content.split()),
                embedding_id=f"{doc.id}_{idx}",  # Unique ID for Qdrant
                acl_json={
                    'space_key': 'ENG',
                    'space_name': 'Engineering',
                    'connector_type': 'confluence',
                    'requires_space_permission': True
                }
            )
            
            db.add(chunk)
            db.flush()  # Get the chunk ID
            
            # Index in Qdrant
            payload = {
                "chunk_id": chunk.id,
                "document_id": doc.id,
                "workspace_id": doc.workspace_id,
                "source_type": doc.source_type,
                "source_id": doc.source_id,
                "title": doc.title,
                "url": doc.url or "",
                "content": chunk_content,
                "chunk_index": idx
            }
            
            qdrant_client.upsert(
                collection_name="documents",
                points=[PointStruct(
                    id=chunk.id,  # Use chunk ID, not document ID
                    vector=embedding_vector,
                    payload=payload
                )]
            )
        
        db.commit()
        logger.info(f"✅ Successfully indexed {len(chunks)} chunks!")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    resync_sdk_doc()
