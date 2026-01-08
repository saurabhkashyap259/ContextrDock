"""Celery task for syncing connector data."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.database import get_db
from src.ingestion.pipeline import ingest_document
from src.models.connector import Connector
from src.models.sync_run import SyncRun, SyncStatus
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class CredentialRefreshManager:
    """
    Manager for OAuth credential refresh with retry logic (T194).

    Features:
    - Exponential backoff: 1min, 5min, 15min
    - Automatic retry on transient failures
    - Token refresh via OAuth provider
    """

    def __init__(self):
        self.retry_delays = [60, 300, 900]  # 1min, 5min, 15min in seconds

    async def refresh_credential(
        self,
        connector: Connector,
        oauth_client: any,
    ) -> dict[str, Any]:
        """
        Refresh OAuth credential with retry logic.

        Args:
            connector: Connector with OAuth credentials
            oauth_client: OAuth client for token refresh

        Returns:
            Dict with refreshed tokens

        Raises:
            Exception: If all retry attempts fail
        """
        refresh_token = connector.credentials.get("refresh_token")
        if not refresh_token:
            raise Exception("No refresh_token available for credential refresh")

        for attempt, delay in enumerate(self.retry_delays):
            try:
                # Attempt refresh
                new_tokens = await oauth_client.refresh_tokens(
                    refresh_token=refresh_token
                )

                logger.info(
                    f"Successfully refreshed OAuth credential for connector {connector.id} "
                    f"(attempt {attempt + 1})"
                )

                return new_tokens

            except Exception as e:
                logger.warning(
                    f"OAuth refresh failed for connector {connector.id} "
                    f"(attempt {attempt + 1}/{len(self.retry_delays)}): {e}"
                )

                if attempt < len(self.retry_delays) - 1:
                    # Wait before retry
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    logger.error(
                        f"Failed to refresh OAuth credential for connector {connector.id} "
                        f"after {len(self.retry_delays)} attempts"
                    )
                    raise

        raise Exception("Unexpected refresh failure")

    def is_credential_expired(self, connector: Connector, buffer_minutes: int = 5) -> bool:
        """
        Check if connector's OAuth credential is expired or expires soon.

        Args:
            connector: Connector to check
            buffer_minutes: Buffer time before expiration to trigger refresh

        Returns:
            True if credential is expired or expires within buffer time
        """
        if not connector.credentials:
            return False

        expires_at_str = connector.credentials.get("expires_at")
        if not expires_at_str:
            return False

        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            buffer_time = datetime.now(UTC) + timedelta(minutes=buffer_minutes)
            return expires_at <= buffer_time
        except (ValueError, TypeError):
            logger.warning(f"Invalid expires_at format for connector {connector.id}")
            return False


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
def run_connector_sync(self, connector_id: int) -> dict[str, Any]:
    """Sync connector data and ingest into pipeline (T194: with OAuth refresh).

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

        # Check and refresh OAuth credential if needed (T194)
        refresh_manager = CredentialRefreshManager()
        if refresh_manager.is_credential_expired(connector):
            logger.info(
                f"OAuth credential expired or expires soon for connector {connector_id}, "
                "refreshing..."
            )

            try:
                # Get OAuth client for connector type
                oauth_client = _get_oauth_client(connector.connector_type)

                # Refresh credential (async call wrapped in sync context)
                new_tokens = asyncio.run(
                    refresh_manager.refresh_credential(connector, oauth_client)
                )

                # Update connector credentials
                connector.credentials = {
                    **connector.credentials,
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens.get(
                        "refresh_token",
                        connector.credentials.get("refresh_token")
                    ),
                    "expires_at": (
                        datetime.now(UTC) + timedelta(seconds=new_tokens["expires_in"])
                    ).isoformat(),
                }
                db.commit()

                logger.info(f"Successfully refreshed OAuth credential for connector {connector_id}")

            except Exception as e:
                logger.error(
                    f"Failed to refresh OAuth credential for connector {connector_id}: {e}"
                )
                # Continue with sync attempt using existing credential
                # (may fail if truly expired)

        # Create sync run
        sync_run = SyncRun(
            connector_id=connector_id,
            status=SyncStatus.RUNNING,
            started_at=datetime.now(UTC),
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
            sync_run.completed_at = datetime.now(UTC)
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
            sync_run.completed_at = datetime.now(UTC)
            sync_run.error_message = str(e)
            db.commit()

            logger.error(f"Sync failed for connector {connector_id}: {e}")
            raise

    finally:
        db.close()


def _get_oauth_client(connector_type: str):
    """
    Get OAuth client for connector type (T194).

    Args:
        connector_type: Connector type (slack, jira, etc.)

    Returns:
        OAuth client instance

    Raises:
        ImportError: If connector type doesn't support OAuth
    """
    # Map connector types to OAuth clients
    # This would be implemented in each connector module
    oauth_clients = {
        "slack": "src.connectors.slack.SlackOAuthClient",
        "jira": "src.connectors.jira.JiraOAuthClient",
        "confluence": "src.connectors.confluence.ConfluenceOAuthClient",
        "github": "src.connectors.github.GitHubOAuthClient",
        "figma": "src.connectors.figma.FigmaOAuthClient",
        "dropbox": "src.connectors.dropbox.DropboxOAuthClient",
    }

    if connector_type not in oauth_clients:
        raise ImportError(f"No OAuth client for connector type: {connector_type}")

    # Import and instantiate OAuth client
    class_path = oauth_clients[connector_type]
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    oauth_client_class = getattr(module, class_name)

    return oauth_client_class()
