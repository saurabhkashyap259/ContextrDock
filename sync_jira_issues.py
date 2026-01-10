#!/usr/bin/env python3
"""Sync JIRA issues to ContextDock.

Fetches issues from JIRA Cloud and indexes them for search.
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(__file__))

from src.models.connector import Connector
from src.models.document import Document
from src.models.document_chunk import DocumentChunk
from src.connectors.jira.connector import JiraConnector
from src.database import SessionLocal
from src.integrations.llm_client import OpenAIClient
from src.integrations.vector_db import QdrantVectorDB
from src.config.settings import settings

load_dotenv()


def sync_jira():
    """Sync JIRA issues to database and vector store."""
    
    print("🎫 Starting JIRA sync...\n")
    
    db = SessionLocal()
    
    try:
        # Get JIRA connector
        connector = db.query(Connector).filter(
            Connector.connector_type == "jira",
            Connector.is_active == True
        ).first()
        
        if not connector:
            print("❌ No active JIRA connector found.")
            print("   Run: python setup_jira.py")
            return
        
        print(f"📊 Connector: {connector.name} (ID: {connector.id})")
        
        # Initialize connector
        jira_connector = JiraConnector(connector)
        
        # Get configuration
        projects = connector.config_json.get("projects", [])
        jql_filter = connector.config_json.get("jql_filter", "")
        
        if projects:
            print(f"🔄 Syncing issues from projects: {', '.join(projects)}")
        
        if jql_filter:
            print(f"🔍 Using JQL filter: {jql_filter}")
        
        print()
        
        # Initialize OpenAI client for embeddings
        openai_client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
        
        # Initialize vector DB
        vector_db = QdrantVectorDB(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection_name
        )
        
        # Sync issues
        synced_count = 0
        start_time = time.time()
        
        for issue_data in jira_connector.sync():
            try:
                # Check if document exists
                existing_doc = db.query(Document).filter(
                    Document.source_id == issue_data["source_id"]
                ).first()
                
                if existing_doc:
                    # Update existing
                    existing_doc.title = issue_data["title"]
                    existing_doc.url = issue_data["url"]
                    existing_doc.content_hash = issue_data["content_hash"]
                    existing_doc.metadata_json = issue_data["metadata"]
                    existing_doc.last_indexed_at = datetime.utcnow()
                    
                    document = existing_doc
                else:
                    # Create new document
                    document = Document(
                        workspace_id=connector.workspace_id,
                        connector_id=connector.id,
                        source_type=issue_data["source_type"],
                        source_id=issue_data["source_id"],
                        title=issue_data["title"],
                        url=issue_data["url"],
                        content_hash=issue_data["content_hash"],
                        metadata_json=issue_data["metadata"],
                        last_indexed_at=datetime.utcnow()
                    )
                    db.add(document)
                
                db.commit()
                
                # Generate embedding and create chunk
                content = issue_data["content"]
                
                # Delete old chunks
                db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document.id
                ).delete()
                
                # Create chunk
                try:
                    # Generate embedding
                    embedding_response = openai_client.create_embedding(content)
                    embedding_vector = embedding_response["data"][0]["embedding"]
                    
                    # Create chunk
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=0,
                        content=content,
                        token_count=len(content.split()),  # Rough estimate
                        embedding_id=f"{document.id}_0",
                        acl_json=issue_data["acl"]
                    )
                    
                    db.add(chunk)
                    db.commit()
                    
                    # Index in Qdrant
                    vector_db.upsert_vectors([{
                        "id": chunk.embedding_id,
                        "vector": embedding_vector,
                        "payload": {
                            "chunk_id": chunk.id,
                            "document_id": document.id,
                            "content": content[:500],  # Store snippet
                            "title": document.title,
                            "source_type": document.source_type,
                            "acl": issue_data["acl"]
                        }
                    }])
                    
                    synced_count += 1
                    issue_key = issue_data["metadata"].get("issue_key", "")
                    print(f"✅ Synced issue {issue_key}: {document.title}")
                    
                except Exception as e:
                    print(f"⚠️  Failed to index {issue_data['source_id']}: {e}")
                    db.rollback()
                
            except Exception as e:
                print(f"❌ Error processing issue: {e}")
                db.rollback()
                continue
        
        duration = time.time() - start_time
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        
        print(f"\n🎉 Sync complete!")
        print(f"   Synced: {synced_count} issues")
        print(f"   Duration: {minutes}m {seconds}s")
        
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sync_jira()
