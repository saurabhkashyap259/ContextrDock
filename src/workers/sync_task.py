"""Celery task for syncing connector data."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from src.database import get_db
from src.models.connector import Connector
from src.models.sync_run import SyncRun, SyncStatus
from src.ingestion.pipeline import ingest_document
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_connector_class(connector_type: str):
    """Get connector class by type.

    Args:
        connector_type: Connector type (slack, jira, etc.)

    Returns:
        Connector class

    Raises:
        ImportError: If connector module not found
    """
    module_map = {
        "slack": "src.connectors.slack",
        "jira": "src.connectors.jira",
        "confluence": "src.connectors.confluence",
        "github": "src.connectors.github",
        "figma": "src.connectors.figma",
        "dropbox": "src.connectors.dropbox",
    }

    if connector_type not in module_map:
        raise ImportError(f"Unknown connector type: {connector_type}")

    module_path = module_map[connector_type]
    module = __import__(module_path, fromlist=["get_connector_class"])
    return module.get_connector_class()


@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def run_connector_sync(self, connector_id: int) -> Dict[str, Any]:
    """Sync connector data and ingest into pipeline.

    Args:
        self: Celery task instance (bound)
        connector_id: ID of connector to sync

    Returns:
        Dict with sync results (status, documents_added, etc.)

    Raises:
        Exception: If sync fails after retries
    """
    db: Session = next(get_db())

    try:
        # Fetch connector
        connector = db.query(Connector).filter_by(id=connector_id).first()
        if not connector:
            raise Exception(f"Connector {connector_id} not found")

        # Skip inactive connectors
        if not connector.is_active:
            logger.info(f"Connector {connector_id} is inactive, skipping sync")
            return {
                "status": "skipped",
                "message": "Connector is inactive",
            }

        # Create sync run
        sync_run = SyncRun(
            connector_id=connector_id,
            status=SyncStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        db.add(sync_run)
        db.commit()

        logger.info(
            f"Starting sync for connector {connector_id} ({connector.connector_type})"
        )

        try:
            # Get connector class
            connector_class = get_connector_class(connector.connector_type)
            connector_instance = connector_class(connector)

            # Get previous cursor state for incremental sync
            cursor_state = None
            previous_run = (
                db.query(SyncRun)
                .filter_by(connector_id=connector_id, status=SyncStatus.COMPLETED)
                .order_by(SyncRun.completed_at.desc())
                .first()
            )
            if previous_run and previous_run.cursor_state:
                cursor_state = previous_run.cursor_state
                logger.info(f"Using cursor state from previous run: {cursor_state}")

            # Sync documents
            documents_processed = 0
            documents_added = 0
            documents_updated = 0
            documents_failed = 0

            for document in connector_instance.sync(cursor_state=cursor_state):
                try:
                    # Process document through ingestion pipeline
                    ingested_doc = ingest_document(
                        db_session=db,
                        workspace_id=connector.workspace_id,
                        connector_id=connector_id,
                        source_type=document["source_type"],
                        source_id=document["source_id"],
                        title=document["title"],
                        content=document["content"],
                        url=document.get("source_url"),
                        acl=document.get("acl"),
                        metadata=document.get("metadata", {}),
                    )

                    documents_processed += 1
                    
                    # Check if document was updated (has previous version)
                    if ingested_doc.document_chunks:
                        # If document already existed, it was updated
                        documents_updated += 1
                    else:
                        documents_added += 1

                except Exception as e:
                    logger.error(
                        f"Failed to process document {document.get('source_id')}: {e}"
                    )
                    documents_failed += 1

            # Get final cursor state if connector supports it
            new_cursor_state = None
            if hasattr(connector_instance, "get_cursor_state"):
                new_cursor_state = connector_instance.get_cursor_state()

            # Update sync run
            sync_run.status = SyncStatus.COMPLETED
            sync_run.completed_at = datetime.now(timezone.utc)
            sync_run.documents_added = documents_added
            sync_run.documents_updated = documents_updated
            sync_run.documents_deleted = 0  # Not implemented yet
            sync_run.cursor_state = new_cursor_state

            db.commit()

            logger.info(
                f"Sync completed for connector {connector_id}: "
                f"{documents_added} added, {documents_updated} updated, "
                f"{documents_failed} failed"
            )

            return {
                "status": "success",
                "documents_processed": documents_processed,
                "documents_added": documents_added,
                "documents_updated": documents_updated,
                "documents_failed": documents_failed,
                "cursor_state": new_cursor_state,
            }

        except Exception as e:
            # Update sync run with error
            sync_run.status = SyncStatus.FAILED
            sync_run.completed_at = datetime.now(timezone.utc)
            sync_run.error_message = str(e)
            db.commit()

            logger.error(f"Sync failed for connector {connector_id}: {e}")
            raise

    finally:
        db.close()
