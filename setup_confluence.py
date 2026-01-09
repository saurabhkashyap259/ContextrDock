#!/usr/bin/env python3
"""Setup and sync Confluence connector.

This script helps you:
1. Create Confluence connector in database
2. Configure OAuth credentials
3. Sync pages and spaces
4. Index content in vector database

Usage:
    python setup_confluence.py --help
    python setup_confluence.py setup --instance-url https://yourcompany.atlassian.net
    python setup_confluence.py sync --connector-id 1
    python setup_confluence.py sync --all  # Sync all pages
"""

import argparse
import logging
import sys
from datetime import datetime
from typing import List

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select

from src.config.settings import Settings
from src.connectors.confluence.connector import ConfluenceConnector
from src.connectors.sdk import OAuth2Token
from src.database import SessionLocal
from src.models.connector import Connector
from src.models.connector_definition import ConnectorDefinition
from src.models.document import Document
from src.models.workspace import Workspace

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client for embeddings
settings = Settings()
openai_client = OpenAI(api_key=settings.openai_api_key)
qdrant_client = QdrantClient(url=settings.qdrant_url)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def generate_embedding(text: str) -> List[float]:
    """Generate embedding for text using OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Error generating embedding: {e}")
        raise


def create_confluence_connector(
    workspace_id: int,
    instance_url: str,
    access_token: str,
    space_keys: list[str] = None,
) -> Connector:
    """Create Confluence connector in database.

    Args:
        workspace_id: Workspace ID
        instance_url: Confluence instance URL (e.g., https://company.atlassian.net)
        access_token: OAuth2 access token
        space_keys: List of space keys to sync (optional, syncs all if empty)

    Returns:
        Created Connector instance
    """
    db = SessionLocal()

    try:
        # Get or create connector definition
        stmt = select(ConnectorDefinition).where(
            ConnectorDefinition.connector_type == "confluence"
        )
        conn_def = db.execute(stmt).scalar_one_or_none()

        if not conn_def:
            logger.info("Creating Confluence connector definition")
            conn_def = ConnectorDefinition(
                name="Confluence",
                connector_type="confluence",
                description="Confluence Cloud connector for pages and spaces",
                config_schema={},
                oauth_scopes=[
                    "read:confluence-content.all",
                    "read:confluence-space.summary",
                ],
                supports_read=True,
                supports_write=True,  # For creating pages
            )
            db.add(conn_def)
            db.commit()
            db.refresh(conn_def)

        # Create connector
        config_json = {"instance_url": instance_url}
        if space_keys:
            config_json["space_keys"] = space_keys

        connector = Connector(
            connector_definition_id=conn_def.id,
            workspace_id=workspace_id,
            name="Confluence",
            config_json=config_json,
            credentials={
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read:confluence-content.all",
                "expires_at": datetime.now().timestamp() + 3600,
            },
            sync_schedule="6-hourly",
            is_active=True,
        )

        db.add(connector)
        db.commit()
        db.refresh(connector)

        logger.info(f"Created Confluence connector: {connector.id}")
        return connector

    finally:
        db.close()


def sync_confluence(
    connector_id: int,
    max_pages: int = None,
    reindex: bool = False,
) -> tuple[int, int]:
    """Sync Confluence pages and index them.

    Args:
        connector_id: Connector ID
        max_pages: Maximum pages to sync (None for all)
        reindex: Delete existing documents before syncing

    Returns:
        Tuple of (pages_synced, documents_indexed)
    """
    db = SessionLocal()
    settings = Settings()

    try:
        # Get connector
        connector = db.get(Connector, connector_id)
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        if connector.connector_type != "confluence":
            raise ValueError(f"Connector {connector_id} is not a Confluence connector")

        logger.info(f"Starting Confluence sync for connector {connector_id}")
        logger.info(f"Instance URL: {connector.config_json.get('instance_url')}")

        space_keys = connector.config_json.get("space_keys", [])
        if space_keys:
            logger.info(f"Syncing spaces: {', '.join(space_keys)}")
        else:
            logger.info("Syncing all spaces")

        # Delete existing documents if reindexing
        if reindex:
            logger.info("Deleting existing documents (reindex mode)")
            db.query(Document).filter(
                Document.connector_id == connector_id
            ).delete()
            db.commit()

        # Initialize services
        # Initialize connector
        confluence_connector = ConfluenceConnector(connector)

        # Ensure collection exists
        try:
            qdrant_client.get_collection("documents")
        except Exception:
            qdrant_client.create_collection(
                collection_name="documents",
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSIONS,
                    distance=Distance.COSINE
                )
            )

        # Sync pages
        pages_synced = 0
        documents_indexed = 0

        for doc_data in confluence_connector.sync(max_pages=max_pages):
            # Create document in database
            document = Document(
                connector_id=connector_id,
                workspace_id=connector.workspace_id,
                source_id=doc_data["source_id"],
                source_type=doc_data["source_type"],
                title=doc_data["metadata"].get("page_title", "Untitled"),
                content=doc_data["content"],
                content_type="text/plain",
                metadata_json=doc_data["metadata"],
                acl_metadata=doc_data.get("acl_metadata", {}),
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            pages_synced += 1

            # Generate embedding
            try:
                embedding_vector = generate_embedding(document.content)

                # Index in vector database
                qdrant_client.upsert(
                    collection_name="documents",
                    points=[PointStruct(
                        id=document.id,
                        vector=embedding_vector,
                        payload={
                            "title": document.title,
                            "source_type": document.source_type,
                            "source_id": document.source_id,
                            "workspace_id": document.workspace_id,
                            "connector_id": document.connector_id,
                            **document.metadata_json,
                        }
                    )]
                )

                # Update document with embedding status
                document.embedding_status = "completed"
                document.indexed_at = datetime.now()
                db.commit()

                documents_indexed += 1

                if pages_synced % 10 == 0:
                    logger.info(
                        f"Progress: {pages_synced} pages synced, {documents_indexed} indexed"
                    )

            except Exception as e:
                logger.error(f"Failed to index document {document.id}: {e}")
                document.embedding_status = "failed"
                db.commit()

        logger.info(f"Sync complete: {pages_synced} pages, {documents_indexed} indexed")
        return pages_synced, documents_indexed

    finally:
        db.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Setup and sync Confluence connector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Create Confluence connector")
    setup_parser.add_argument(
        "--instance-url",
        required=True,
        help="Confluence instance URL (e.g., https://company.atlassian.net)",
    )
    setup_parser.add_argument(
        "--access-token",
        required=True,
        help="OAuth2 access token for Confluence API",
    )
    setup_parser.add_argument(
        "--workspace-id",
        type=int,
        default=1,
        help="Workspace ID (default: 1)",
    )
    setup_parser.add_argument(
        "--spaces",
        help="Comma-separated list of space keys to sync (e.g., ENG,DOCS)",
    )

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync Confluence pages")
    sync_parser.add_argument(
        "--connector-id",
        type=int,
        help="Connector ID to sync",
    )
    sync_parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to sync",
    )
    sync_parser.add_argument(
        "--all",
        action="store_true",
        help="Sync all pages (no limit)",
    )
    sync_parser.add_argument(
        "--reindex",
        action="store_true",
        help="Delete existing documents and reindex",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "setup":
            space_keys = None
            if args.spaces:
                space_keys = [s.strip() for s in args.spaces.split(",")]

            connector = create_confluence_connector(
                workspace_id=args.workspace_id,
                instance_url=args.instance_url,
                access_token=args.access_token,
                space_keys=space_keys,
            )

            print(f"\n✅ Confluence connector created!")
            print(f"   Connector ID: {connector.id}")
            print(f"   Instance URL: {connector.config_json['instance_url']}")
            if space_keys:
                print(f"   Spaces: {', '.join(space_keys)}")
            else:
                print("   Spaces: All")
            print(f"\nNext step: python setup_confluence.py sync --connector-id {connector.id}")

        elif args.command == "sync":
            if not args.connector_id:
                print("❌ Error: --connector-id is required for sync command")
                return 1

            max_pages = args.max_pages if not args.all else None

            pages, indexed = sync_confluence(
                connector_id=args.connector_id,
                max_pages=max_pages,
                reindex=args.reindex,
            )

            print(f"\n✅ Sync complete!")
            print(f"   Pages synced: {pages}")
            print(f"   Documents indexed: {indexed}")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
