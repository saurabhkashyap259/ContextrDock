"""Base connector class for all connector implementations."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterator, Dict, List, Any
from sqlalchemy.orm import Session

from src.models.connector import Connector
from src.models.sync_run import SyncRun


class ConnectorBase(ABC):
    """
    Abstract base class for all connector implementations.
    
    Provides lifecycle hooks and helper methods for sync operations,
    pagination, ACL extraction, and cursor state management.
    
    Subclasses must implement:
    - sync(): Main sync method that yields documents
    - fetch_page(): Paginated API fetching with cursor support
    - extract_acl(): Extract access control list from documents
    
    Example:
        class SlackConnector(ConnectorBase):
            def sync(self) -> Iterator[Dict[str, Any]]:
                cursor = self.load_cursor_state().get("cursor")
                while True:
                    messages, next_cursor = self.fetch_page(cursor)
                    for msg in messages:
                        yield {
                            "title": msg["text"][:50],
                            "content": msg["text"],
                            "source_id": msg["ts"],
                            "source_url": f"https://slack.com/archives/{msg['channel']}/{msg['ts']}",
                            "metadata": {"channel": msg["channel"], "author": msg["user"]}
                        }
                    if not next_cursor:
                        break
                    cursor = next_cursor
                    self.save_cursor_state({"cursor": cursor})
    """
    
    def __init__(self, connector: Connector, db_session: Session):
        """
        Initialize connector with configuration and database session.
        
        Args:
            connector: Connector model instance with config and credentials
            db_session: SQLAlchemy session for database operations
        """
        self.connector = connector
        self.db_session = db_session
    
    @abstractmethod
    def sync(self) -> Iterator[Dict[str, Any]]:
        """
        Main sync method that yields documents from the connector.
        
        Must be implemented by all subclasses. Should handle pagination,
        incremental sync using cursor state, and yield documents in the
        standardized format.
        
        Yields:
            Document dictionaries with keys:
            - title: Document title or summary (str)
            - content: Full document content (str)
            - source_id: Unique ID from source system (str)
            - source_url: Deep link to original content (str)
            - metadata: Connector-specific metadata (dict)
            - acl: Optional list of user emails with access (list[str])
        
        Raises:
            Exception: Any errors during sync (will be caught and logged by sync runner)
        """
        pass
    
    @abstractmethod
    def fetch_page(self, cursor: str | None = None) -> tuple[List[Dict[str, Any]], str | None]:
        """
        Fetch a single page of data from the connector API.
        
        Must be implemented by all subclasses. Should handle cursor-based
        pagination and return both the data and the next cursor.
        
        Args:
            cursor: Pagination cursor from previous page, None for first page
        
        Returns:
            Tuple of (page_data, next_cursor):
            - page_data: List of items from this page
            - next_cursor: Cursor for next page, None if no more pages
        
        Raises:
            Exception: Any errors during API call (rate limits, auth failures, etc.)
        """
        pass
    
    @abstractmethod
    def extract_acl(self, document: Dict[str, Any]) -> List[str]:
        """
        Extract access control list from a document.
        
        Must be implemented by all subclasses. Should return list of user
        emails who have access to this document based on connector-specific
        permissions (channel membership, project roles, file permissions, etc.).
        
        Args:
            document: Document dictionary with metadata
        
        Returns:
            List of user email addresses with access to this document
        
        Example:
            For Slack: Return all members of the channel
            For Jira: Return users with issue view permission
            For Confluence: Return users with page view permission
        """
        pass
    
    def load_cursor_state(self) -> Dict[str, Any]:
        """
        Load cursor state from connector for incremental sync.
        
        Returns cursor state from last successful sync, enabling incremental
        syncs that only fetch new/updated content.
        
        Returns:
            Dictionary with cursor state (page tokens, timestamps, etc.)
            Empty dict if no previous sync or first sync.
        """
        return self.connector.cursor_state_json or {}
    
    def save_cursor_state(self, state: Dict[str, Any]) -> None:
        """
        Save cursor state to connector for next incremental sync.
        
        Persists current sync position (page tokens, last timestamp, etc.)
        to enable resuming from this point in future syncs.
        
        Args:
            state: Dictionary with cursor state to save
        """
        self.connector.cursor_state_json = state
        self.db_session.commit()
    
    def create_sync_run(self) -> SyncRun:
        """
        Create a new SyncRun record for tracking this sync operation.
        
        Creates a SyncRun with status="running" and started_at timestamp.
        Used by sync runners to track progress, errors, and results.
        
        Returns:
            New SyncRun instance with running status
        """
        sync_run = SyncRun(
            connector_id=self.connector.id,
            status="running",
            started_at=datetime.now(timezone.utc)
        )
        self.db_session.add(sync_run)
        self.db_session.commit()
        return sync_run
    
    def complete_sync_run(
        self,
        sync_run: SyncRun,
        status: str,
        documents_added: int = 0,
        documents_updated: int = 0,
        documents_deleted: int = 0,
        error_message: str | None = None
    ) -> None:
        """
        Complete a sync run with final status and statistics.
        
        Updates SyncRun with completion time, status, document counts,
        and optional error message if sync failed.
        
        Args:
            sync_run: SyncRun instance to complete
            status: Final status ("completed", "failed", "cancelled")
            documents_added: Count of new documents indexed
            documents_updated: Count of existing documents updated
            documents_deleted: Count of documents removed
            error_message: Error details if status is "failed"
        """
        sync_run.status = status
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.documents_added = documents_added
        sync_run.documents_updated = documents_updated
        sync_run.documents_deleted = documents_deleted
        
        if error_message:
            sync_run.error_message = error_message
        
        self.db_session.commit()
    
    def update_last_synced_at(self) -> None:
        """
        Update connector's last_synced_at timestamp to current time.
        
        Called after successful sync to track when connector was last synced.
        Used for monitoring and scheduling future syncs.
        """
        self.connector.last_synced_at = datetime.now(timezone.utc)
        self.db_session.commit()
