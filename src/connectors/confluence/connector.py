"""Confluence connector implementation.

Fetches pages, blog posts, and spaces from Confluence Cloud instances.
Supports incremental sync using lastModified timestamps.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Optional

import requests

from src.connectors.sdk import (
    ConnectorBase,
    OAuth2Token,
    rate_limit,
)
from src.models.connector import Connector

logger = logging.getLogger(__name__)


class ConfluenceConnector(ConnectorBase):
    """Confluence Cloud connector.

    Fetches:
    - Pages with content (title, body, hierarchy)
    - Blog posts
    - Space metadata for ACL
    - Page restrictions and space permissions

    OAuth Scopes Required:
    - read:confluence-content.all - Read pages, blogs, spaces
    - read:confluence-space.summary - Read space information
    """

    RATE_LIMIT_CALLS = 10  # Confluence Cloud: 10 requests per second
    RATE_LIMIT_PERIOD = 1  # seconds

    def __init__(self, connector: Connector, db_session: Optional[Any] = None):
        """Initialize Confluence connector.

        Args:
            connector: Connector model instance with credentials and config
            db_session: Optional database session (not used for API operations)
        """
        super().__init__(connector, db_session)
        self._oauth_token: Optional[OAuth2Token] = None
        self._spaces_cache: dict[str, dict[str, Any]] = {}

        # Get Confluence instance URL from config
        self.instance_url = self.connector.config_json.get("instance_url", "")
        if not self.instance_url:
            raise ValueError("Confluence instance_url is required in connector config")

        # Remove trailing slash
        self.instance_url = self.instance_url.rstrip("/")
        self.api_base = f"{self.instance_url}/wiki/rest/api"

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with authorization."""
        if self._oauth_token is None:
            # Load token from connector credentials
            creds = self.connector.credentials
            if not creds:
                raise ValueError("No credentials found for Confluence connector")
                
            access_token = creds.get("access_token", "")
            if not access_token:
                raise ValueError("No access_token in Confluence credentials")
            
            # Check if this is an API token (Basic Auth) or OAuth token
            # API tokens are base64 encoded email:token
            # OAuth tokens start with 'eyJ' (JWT format)
            if access_token.startswith("eyJ"):
                # OAuth token
                self._oauth_token = OAuth2Token(
                    access_token=access_token,
                    token_type=creds.get("token_type", "Bearer"),
                    expires_in=creds.get("expires_in", 3600),
                    refresh_token=creds.get("refresh_token"),
                    scope=creds.get("scope", ""),
                )
                return {
                    "Authorization": f"Bearer {self._oauth_token.access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            else:
                # API token with Basic Auth
                return {
                    "Authorization": f"Basic {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }

        # OAuth token path
        return {
            "Authorization": f"Bearer {self._oauth_token.access_token}" if self._oauth_token else "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_spaces_page(
        self, start: int = 0, limit: int = 25
    ) -> dict[str, Any]:
        """Fetch page of spaces from Confluence API.

        Args:
            start: Pagination offset
            limit: Number of spaces per page

        Returns:
            API response with spaces list and pagination info
        """
        url = f"{self.api_base}/space"
        params = {
            "start": start,
            "limit": limit,
            "expand": "permissions,description.plain",
        }

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_pages_page(
        self,
        space_key: Optional[str] = None,
        start: int = 0,
        limit: int = 25,
        expand: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch page of content (pages/blogs) from Confluence API.

        Args:
            space_key: Filter by space key
            start: Pagination offset
            limit: Number of items per page
            expand: Comma-separated list of properties to expand

        Returns:
            API response with content list and pagination info
        """
        url = f"{self.api_base}/content"

        if expand is None:
            expand = "body.storage,space,version,ancestors,restrictions.read.restrictions.user"

        params = {
            "start": start,
            "limit": limit,
            "expand": expand,
            "type": "page",  # Can be page, blogpost, comment
        }

        if space_key:
            params["spaceKey"] = space_key

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_page_restrictions(self, page_id: str) -> dict[str, Any]:
        """Fetch restrictions for a specific page.

        Args:
            page_id: Confluence page ID

        Returns:
            Restrictions data including users and groups
        """
        url = f"{self.api_base}/content/{page_id}/restriction"
        params = {
            "expand": "restrictions.user,restrictions.group",
        }

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        return data

    def _load_spaces_cache(self) -> None:
        """Load all spaces into cache for metadata enrichment."""
        logger.info("Loading Confluence spaces into cache")

        start = 0
        limit = 25

        while True:
            spaces_data = self._fetch_spaces_page(start=start, limit=limit)

            results = spaces_data.get("results", [])
            if not results:
                break

            for space in results:
                space_key = space.get("key")
                if space_key:
                    self._spaces_cache[space_key] = space

            # Check if there are more spaces
            size = spaces_data.get("size", 0)
            if size < limit:
                break

            start += limit

        logger.info(f"Loaded {len(self._spaces_cache)} spaces into cache")

    def sync(
        self,
        cursor_state: Optional[dict[str, Any]] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Sync pages from Confluence instance.

        Args:
            cursor_state: State from previous sync for incremental updates
            max_pages: Limit number of pages to sync (for testing)

        Yields:
            Document dicts with content, metadata, and acl_metadata
        """
        logger.info(f"Starting Confluence sync for connector {self.connector.id}")

        # Load spaces into cache
        self._load_spaces_cache()

        # Get configured space keys
        space_keys = self.connector.config_json.get("space_keys", [])

        # If no spaces configured, sync all spaces
        if not space_keys:
            space_keys = list(self._spaces_cache.keys())

        pages_processed = 0

        for space_key in space_keys:
            if max_pages and pages_processed >= max_pages:
                break

            logger.info(f"Syncing space: {space_key}")

            # Fetch pages from space
            start = 0
            limit = 25

            while True:
                if max_pages and pages_processed >= max_pages:
                    break

                pages_data = self._fetch_pages_page(
                    space_key=space_key, start=start, limit=limit
                )

                results = pages_data.get("results", [])
                if not results:
                    break

                for page in results:
                    if max_pages and pages_processed >= max_pages:
                        break

                    # Extract page details
                    page_id = page.get("id")
                    page_title = page.get("title", "")
                    page_type = page.get("type", "page")

                    # Get body content
                    body = page.get("body", {})
                    storage = body.get("storage", {})
                    content_html = storage.get("value", "")

                    # Get version info
                    version = page.get("version", {})
                    version_number = version.get("number", 1)
                    last_modified = version.get("when")

                    # Get space info
                    space = page.get("space", {})
                    space_key_actual = space.get("key", space_key)
                    space_name = space.get("name", "")

                    # Get ancestors (parent pages)
                    ancestors = page.get("ancestors", [])
                    parent_id = ancestors[-1].get("id") if ancestors else None
                    parent_title = ancestors[-1].get("title") if ancestors else None

                    # Build document content
                    content_parts = [f"Page: {page_title}"]
                    if content_html:
                        # Strip HTML tags for text content (simplified)
                        import re
                        text_content = re.sub(r'<[^>]+>', ' ', content_html)
                        text_content = re.sub(r'\s+', ' ', text_content).strip()
                        if text_content:
                            content_parts.append(f"\n{text_content}")

                    content = "\n".join(content_parts)

                    # Build metadata
                    metadata = {
                        "page_id": page_id,
                        "page_title": page_title,
                        "page_type": page_type,
                        "space_key": space_key_actual,
                        "space_name": space_name,
                        "version": version_number,
                        "last_modified": last_modified,
                        "source_url": f"{self.instance_url}/wiki/spaces/{space_key_actual}/pages/{page_id}",
                    }

                    if parent_id:
                        metadata["parent_id"] = parent_id
                        metadata["parent_title"] = parent_title

                    # Get page restrictions
                    try:
                        restrictions_data = self._fetch_page_restrictions(page_id)
                        read_restrictions = restrictions_data.get("read", {})

                        # Extract restricted users
                        user_restrictions = read_restrictions.get("restrictions", {}).get("user", {})
                        restricted_users = user_restrictions.get("results", [])

                        if restricted_users:
                            metadata["restricted_users"] = [
                                u.get("accountId") for u in restricted_users
                            ]

                        # Extract restricted groups
                        group_restrictions = read_restrictions.get("restrictions", {}).get("group", {})
                        restricted_groups = group_restrictions.get("results", [])

                        if restricted_groups:
                            metadata["restricted_groups"] = [
                                g.get("name") for g in restricted_groups
                            ]
                    except Exception as e:
                        logger.warning(f"Failed to fetch restrictions for page {page_id}: {e}")

                    # Extract ACL metadata
                    acl_metadata = self.extract_acl(metadata)

                    # Yield page document
                    document = {
                        "source_id": f"confluence_{page_id}",
                        "source_type": "confluence",
                        "content": content,
                        "metadata": metadata,
                        "acl_metadata": acl_metadata,
                    }
                    yield document

                    pages_processed += 1

                # Check if there are more pages
                size = pages_data.get("size", 0)
                if size < limit:
                    break

                start += limit

        # Update cursor state
        self._cursor_state = {
            "last_sync_timestamp": datetime.now().isoformat(),
        }

        logger.info(f"Confluence sync complete: {pages_processed} pages processed")

    def fetch_page(
        self, page_cursor: Optional[str] = None, page_size: int = 25
    ) -> dict[str, Any]:
        """Fetch a page of content (for API compatibility).

        Args:
            page_cursor: Pagination cursor (start as string)
            page_size: Number of items per page

        Returns:
            Page of content with cursor
        """
        start = int(page_cursor) if page_cursor else 0
        data = self._fetch_pages_page(start=start, limit=page_size)

        results = data.get("results", [])
        size = data.get("size", 0)
        next_start = start + size

        return {
            "items": results,
            "next_cursor": str(next_start) if size == page_size else None,
            "has_more": size == page_size,
        }

    def extract_acl(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Extract ACL metadata from document metadata.

        Args:
            metadata: Document metadata with space and restriction info

        Returns:
            ACL metadata with access control rules
        """
        space_key = metadata.get("space_key")
        restricted_users = metadata.get("restricted_users", [])
        restricted_groups = metadata.get("restricted_groups", [])

        acl = {
            "space_key": space_key,
            "connector_type": "confluence",
        }

        # Check if page has restrictions
        if restricted_users or restricted_groups:
            # Page-level restrictions
            acl["access_level"] = "restricted"
            acl["allowed_users"] = restricted_users
            acl["allowed_groups"] = restricted_groups
        else:
            # Space-level access
            acl["access_level"] = "space"
            acl["requires_space_permission"] = True

        # Get space permissions from cache
        if space_key in self._spaces_cache:
            space = self._spaces_cache[space_key]
            space_name = space.get("name")
            acl["space_name"] = space_name

            # Check space type (global, personal)
            space_type = space.get("type")
            if space_type:
                acl["space_type"] = space_type

        return acl
