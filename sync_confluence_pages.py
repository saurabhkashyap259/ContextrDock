#!/usr/bin/env python3
"""Simple Confluence sync script - syncs pages to database and Qdrant.

Based on sync_slack_messages.py pattern.
"""

import argparse
import logging
import sys
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config.settings import Settings
from src.connectors.confluence.connector import ConfluenceConnector
from src.database import SessionLocal
from src.models.connector import Connector
from src.models.document import Document
from src.models.document_chunk import DocumentChunk

# Load environment
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize clients
settings = Settings()
openai_client = OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def generate_embedding(text: str) -> List[float]:
    """Generate embedding using OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Error generating embedding: {e}")
        raise


def sync_confluence(connector_id: int, max_pages: int = None):
    """Sync Confluence pages."""
    db = SessionLocal()
    
    try:
        # Get connector
        connector = db.get(Connector, connector_id)
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")
        
        logger.info(f"Starting sync for connector {connector_id}")
        logger.info(f"Instance: {connector.config_json.get('instance_url')}")
        
        # Ensure Qdrant collection exists
        try:
            qdrant_client.get_collection("documents")
            logger.info("✅ Qdrant collection 'documents' exists")
        except Exception:
            logger.info("Creating Qdrant collection 'documents'")
            qdrant_client.create_collection(
                collection_name="documents",
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE
                )
            )
        
        # Initialize connector
        confluence_connector = ConfluenceConnector(connector, db)
        
        # Sync pages
        pages_synced = 0
        documents_indexed = 0
        
        for doc_data in confluence_connector.sync(max_pages=max_pages):
            try:
                # Extract content for embedding (not stored in Document model)
                content = doc_data["content"]
                
                # Create document in database (WITHOUT content field)
                document = Document(
                    connector_id=connector_id,
                    workspace_id=connector.workspace_id,
                    source_id=doc_data["source_id"],
                    source_type=doc_data["source_type"],
                    title=doc_data["metadata"].get("page_title", "Untitled"),
                    url=doc_data.get("source_url", ""),
                    metadata_json=doc_data["metadata"],
                )
                
                db.add(document)
                db.commit()
                db.refresh(document)
                
                pages_synced += 1
                
                # Generate embedding
                embedding_vector = generate_embedding(content)
                
                # Prepare payload for Qdrant
                payload = {
                    "document_id": document.id,
                    "workspace_id": document.workspace_id,
                    "source_type": document.source_type,
                    "source_id": document.source_id,
                    "title": document.title,
                    "url": document.url,
                    "content": content,
                    **doc_data["metadata"],
                }
                
                # Index in Qdrant
                qdrant_client.upsert(
                    collection_name="documents",
                    points=[PointStruct(
                        id=document.id,
                        vector=embedding_vector,
                        payload=payload,
                    )]
                )
                
                # Create DocumentChunk record (Confluence pages are typically single chunks)
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content=content,
                    token_count=len(content.split()),  # Rough token count
                    embedding_id=document.id,
                    acl_json=doc_data.get("acl_metadata", {}),
                )
                
                db.add(chunk)
                db.commit()
                
                documents_indexed += 1
                
                if pages_synced % 10 == 0:
                    logger.info(f"Progress: {pages_synced} pages synced, {documents_indexed} indexed")
                    
            except Exception as e:
                logger.error(f"Error processing page: {e}")
                db.rollback()
                continue
        
        logger.info(f"\n✅ Sync complete!")
        logger.info(f"   Pages synced: {pages_synced}")
        logger.info(f"   Documents indexed: {documents_indexed}")
        
        return pages_synced, documents_indexed
        
    finally:
        db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync Confluence pages")
    parser.add_argument("--connector-id", type=int, required=True, help="Connector ID")
    parser.add_argument("--max-pages", type=int, help="Maximum pages to sync")
    parser.add_argument("--all", action="store_true", help="Sync all pages")
    
    args = parser.parse_args()
    
    try:
        max_pages = None if args.all else args.max_pages
        sync_confluence(args.connector_id, max_pages)
        return 0
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
