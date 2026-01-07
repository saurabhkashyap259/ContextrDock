"""Dropbox connector for syncing files and folders."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import requests

from src.connectors.sdk.base import ConnectorBase
from src.connectors.sdk.rate_limiter import rate_limit
from src.models.connector import Connector


class DropboxConnector(ConnectorBase):
    """Dropbox connector for files, folders, and shared content.

    Syncs:
    - Files and file content
    - Folder structure
    - Shared folders and links
    - File metadata

    OAuth Scopes Required:
    - files.metadata.read: Read file metadata
    - files.content.read: Read file content
    - sharing.read: Read sharing information

    Rate Limits:
    - Not officially published, but typically ~200 requests/minute
    - Uses cursor-based pagination

    ACL:
    - Personal files: Only owner can access
    - Shared folders: Specified members with permissions
    - Shared links: Anyone with link (public) or specific users
    """

    BASE_URL = "https://api.dropboxapi.com"
    CONTENT_URL = "https://content.dropboxapi.com"
    RATE_LIMIT_REQUESTS = 200
    RATE_LIMIT_PERIOD = 60  # 1 minute

    # File types to sync (text-based files only)
    SYNCABLE_EXTENSIONS = {
        ".txt", ".md", ".markdown", ".rst",
        ".pdf", ".doc", ".docx",
        ".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h",
        ".json", ".yaml", ".yml", ".xml", ".csv",
        ".html", ".css", ".scss",
    }

    def __init__(self, connector: Connector):
        """Initialize Dropbox connector.

        Args:
            connector: Connector model instance with Dropbox config
        """
        super().__init__(connector)
        self.config = connector.config or {}
        self.folders = self.config.get("folders", [""])  # Empty string = root
        self.include_shared = self.config.get("include_shared", True)

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Dropbox API.

        Returns:
            Dict with Authorization header
        """
        credentials = getattr(self.connector, "credentials", {})
        access_token = credentials.get("access_token")

        if not access_token:
            raise ValueError("Dropbox access token not found in connector credentials")

        return {
            "Authorization": f"Bearer {access_token}",
        }

    @rate_limit(requests=200, period=60)
    def _list_folder(
        self,
        path: str,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List files and folders in a directory.

        Args:
            path: Folder path (empty string for root)
            cursor: Pagination cursor for continuing

        Returns:
            Dict with entries, cursor, has_more
        """
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        if cursor:
            # Continue with cursor
            url = f"{self.BASE_URL}/2/files/list_folder/continue"
            data = {"cursor": cursor}
        else:
            # Start new listing
            url = f"{self.BASE_URL}/2/files/list_folder"
            data = {
                "path": path,
                "recursive": True,
                "include_deleted": False,
                "include_has_explicit_shared_members": True,
                "include_mounted_folders": True,
            }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()

        return response.json()

    @rate_limit(requests=200, period=60)
    def _download_file(
        self,
        path: str,
    ) -> tuple[bytes, Dict[str, Any]]:
        """Download file content.

        Args:
            path: File path

        Returns:
            Tuple of (content bytes, metadata dict)
        """
        headers = self._get_auth_headers()
        headers["Dropbox-API-Arg"] = json.dumps({"path": path})

        url = f"{self.CONTENT_URL}/2/files/download"

        response = requests.post(url, headers=headers)
        response.raise_for_status()

        # Metadata is in header
        metadata_header = response.headers.get("Dropbox-API-Result", "{}")
        metadata = json.loads(metadata_header)

        return response.content, metadata

    @rate_limit(requests=200, period=60)
    def _list_shared_links(
        self,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List shared links for a path.

        Args:
            path: File or folder path (optional)

        Returns:
            List of shared link dicts
        """
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        url = f"{self.BASE_URL}/2/sharing/list_shared_links"
        data = {}
        if path:
            data["path"] = path

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result.get("links", [])
        except requests.exceptions.HTTPError:
            return []

    def _is_syncable_file(self, filename: str) -> bool:
        """Check if file should be synced based on extension.

        Args:
            filename: File name

        Returns:
            True if file should be synced
        """
        import os
        _, ext = os.path.splitext(filename.lower())
        return ext in self.SYNCABLE_EXTENSIONS

    def _extract_text_content(
        self,
        content_bytes: bytes,
        filename: str,
    ) -> str:
        """Extract text from file content.

        Args:
            content_bytes: File content
            filename: File name for extension detection

        Returns:
            Extracted text or empty string
        """
        import os
        _, ext = os.path.splitext(filename.lower())

        try:
            # Text files
            if ext in {".txt", ".md", ".markdown", ".rst", ".py", ".js", ".ts",
                      ".java", ".go", ".rs", ".cpp", ".c", ".h", ".json",
                      ".yaml", ".yml", ".xml", ".csv", ".html", ".css", ".scss"}:
                return content_bytes.decode("utf-8", errors="ignore")

            # PDF would require library like PyPDF2 (not implemented)
            # DOC/DOCX would require python-docx (not implemented)

            return ""
        except Exception:
            return ""

    def sync(
        self,
        cursor_state: Optional[Dict[str, Any]] = None,
        max_files: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Sync files and folders from Dropbox.

        Args:
            cursor_state: State from previous sync with cursor
            max_files: Maximum number of files to sync (for testing)

        Yields:
            Document dicts with source_id, content, metadata, acl
        """
        cursor = None
        if cursor_state:
            cursor = cursor_state.get("cursor")

        file_count = 0

        for folder_path in self.folders:
            has_more = True

            while has_more:
                result = self._list_folder(path=folder_path, cursor=cursor)
                entries = result.get("entries", [])
                cursor = result.get("cursor")
                has_more = result.get("has_more", False)

                for entry in entries:
                    if max_files and file_count >= max_files:
                        return

                    entry_type = entry.get(".tag")
                    path = entry.get("path_display", "")
                    name = entry.get("name", "")

                    # Only sync files, not folders
                    if entry_type != "file":
                        continue

                    # Check if file type is syncable
                    if not self._is_syncable_file(name):
                        continue

                    # Download file content
                    try:
                        content_bytes, metadata = self._download_file(path)
                        text_content = self._extract_text_content(
                            content_bytes, name
                        )
                    except Exception:
                        # Skip files that can't be downloaded
                        continue

                    # Get sharing info
                    is_shared = entry.get("sharing_info") is not None
                    shared_links = []
                    if self.include_shared:
                        shared_links = self._list_shared_links(path)

                    # Yield file document
                    yield {
                        "source_id": f"dropbox_{entry['id']}",
                        "source_type": "dropbox",
                        "title": name,
                        "content": text_content,
                        "metadata": {
                            "connector_id": self.connector.id,
                            "path": path,
                            "file_name": name,
                            "content_type": "file",
                            "size": metadata.get("size", 0),
                            "modified": metadata.get("client_modified"),
                            "is_shared": is_shared,
                            "shared_link_count": len(shared_links),
                        },
                        "acl": self.extract_acl(entry, shared_links),
                        "source_url": self._build_source_url(path),
                        "timestamp": metadata.get("client_modified"),
                    }

                    file_count += 1

    def _build_source_url(self, path: str) -> str:
        """Build Dropbox web URL for file.

        Args:
            path: File path

        Returns:
            Web URL
        """
        # Encode path for URL
        import urllib.parse
        encoded_path = urllib.parse.quote(path)
        return f"https://www.dropbox.com/home{encoded_path}"

    def extract_acl(
        self,
        entry: Dict[str, Any],
        shared_links: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Extract ACL metadata from file entry.

        Args:
            entry: File entry from API
            shared_links: List of shared links for file

        Returns:
            ACL dict with access_level and allowed_users
        """
        from src.connectors.dropbox.acl import normalize_dropbox_acl

        path = entry.get("path_display", "")
        is_shared = entry.get("sharing_info") is not None

        # Note: Member fetching is expensive, done separately in ACL module
        return normalize_dropbox_acl(
            path=path,
            is_shared=is_shared,
            members=[],
            shared_links=shared_links,
        )
