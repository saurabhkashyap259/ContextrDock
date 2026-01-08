"""Figma connector for syncing design files, comments, and versions."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Optional

import requests

from src.connectors.sdk.base import ConnectorBase
from src.connectors.sdk.rate_limiter import rate_limit
from src.models.connector import Connector


class FigmaConnector(ConnectorBase):
    """Figma connector for design files, comments, and project organization.

    Syncs:
    - Design files with metadata
    - File comments and threads
    - Project organization
    - Team membership

    OAuth Scopes Required:
    - files:read: Read file content
    - file_comments:read: Read comments

    Rate Limits:
    - 100 requests/minute for authenticated requests

    ACL:
    - Team-level: Team members can access
    - Project-level: Project members with permissions
    - File-level: Editors, viewers, commenters
    """

    BASE_URL = "https://api.figma.com"
    RATE_LIMIT_REQUESTS = 100
    RATE_LIMIT_PERIOD = 60  # 1 minute

    def __init__(self, connector: Connector):
        """Initialize Figma connector.

        Args:
            connector: Connector model instance with Figma config
        """
        super().__init__(connector)
        self.config = connector.config or {}
        self.team_id = self.config.get("team_id")
        self.project_ids = self.config.get("project_ids", [])
        self.file_cache: dict[str, dict[str, Any]] = {}

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for Figma API.

        Returns:
            Dict with X-Figma-Token header
        """
        credentials = getattr(self.connector, "credentials", {})
        access_token = credentials.get("access_token")

        if not access_token:
            raise ValueError("Figma access token not found in connector credentials")

        return {
            "X-Figma-Token": access_token,
        }

    @rate_limit(requests=100, period=60)
    def _fetch_team_projects(
        self,
        team_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch projects for a team.

        Args:
            team_id: Figma team ID

        Returns:
            List of project dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/v1/teams/{team_id}/projects"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data.get("projects", [])

    @rate_limit(requests=100, period=60)
    def _fetch_project_files(
        self,
        project_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch files in a project.

        Args:
            project_id: Figma project ID

        Returns:
            List of file dicts with key, name, last_modified
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/v1/projects/{project_id}/files"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data.get("files", [])

    @rate_limit(requests=100, period=60)
    def _fetch_file(
        self,
        file_key: str,
    ) -> dict[str, Any]:
        """Fetch full file content with document tree.

        Args:
            file_key: Figma file key

        Returns:
            File dict with document, name, lastModified
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/v1/files/{file_key}"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

    @rate_limit(requests=100, period=60)
    def _fetch_file_comments(
        self,
        file_key: str,
    ) -> list[dict[str, Any]]:
        """Fetch comments for a file.

        Args:
            file_key: Figma file key

        Returns:
            List of comment dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/v1/files/{file_key}/comments"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data.get("comments", [])

    @rate_limit(requests=100, period=60)
    def _fetch_file_versions(
        self,
        file_key: str,
    ) -> list[dict[str, Any]]:
        """Fetch version history for a file.

        Args:
            file_key: Figma file key

        Returns:
            List of version dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/v1/files/{file_key}/versions"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("versions", [])
        except requests.exceptions.HTTPError:
            # Version history may not be available
            return []

    def _extract_text_from_document(
        self,
        document: dict[str, Any],
    ) -> str:
        """Extract text content from Figma document tree.

        Args:
            document: Document dict with nested children

        Returns:
            Extracted text content
        """
        text_parts = []

        def traverse(node):
            """Recursively traverse document tree."""
            if isinstance(node, dict):
                # Extract text from text nodes
                if node.get("type") == "TEXT":
                    characters = node.get("characters", "")
                    if characters:
                        text_parts.append(characters)

                # Extract frame/component names
                node_name = node.get("name", "")
                if node_name and node.get("type") in ["FRAME", "COMPONENT", "COMPONENT_SET"]:
                    text_parts.append(node_name)

                # Traverse children
                children = node.get("children", [])
                for child in children:
                    traverse(child)

            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(document)
        return " ".join(text_parts)

    def sync(
        self,
        cursor_state: Optional[dict[str, Any]] = None,
        max_files: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Sync design files, comments, and versions from Figma.

        Args:
            cursor_state: State from previous sync with last_updated, synced_files
            max_files: Maximum number of files to sync (for testing)

        Yields:
            Document dicts with source_id, content, metadata, acl
        """
        since_timestamp = None
        synced_files = set()

        if cursor_state:
            since_timestamp = cursor_state.get("last_updated")
            synced_files = set(cursor_state.get("synced_files", []))

        since_dt = None
        if since_timestamp:
            since_dt = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))

        # Fetch team projects
        if not self.team_id:
            raise ValueError("team_id required in connector config")

        projects = self._fetch_team_projects(self.team_id)

        # Filter by project_ids if provided
        if self.project_ids:
            projects = [p for p in projects if p["id"] in self.project_ids]

        file_count = 0

        for project in projects:
            project_id = project["id"]
            project_name = project["name"]

            # Fetch files in project
            files = self._fetch_project_files(project_id)

            for file_meta in files:
                if max_files and file_count >= max_files:
                    return

                file_key = file_meta["key"]
                file_name = file_meta["name"]
                last_modified = file_meta.get("last_modified")

                # Skip if already synced
                if file_key in synced_files:
                    continue

                # Check if modified since last sync
                if since_dt and last_modified:
                    modified_dt = datetime.fromisoformat(
                        last_modified.replace("Z", "+00:00")
                    )
                    if modified_dt <= since_dt:
                        continue

                # Fetch full file content
                file_data = self._fetch_file(file_key)

                # Extract text from document tree
                document = file_data.get("document", {})
                text_content = self._extract_text_from_document(document)

                # Yield file document
                yield {
                    "source_id": f"figma_file_{file_key}",
                    "source_type": "figma",
                    "title": f"Figma File: {file_name}",
                    "content": self._format_file_content(file_data, text_content),
                    "metadata": {
                        "connector_id": self.connector.id,
                        "file_key": file_key,
                        "file_name": file_name,
                        "project_id": project_id,
                        "project_name": project_name,
                        "team_id": self.team_id,
                        "content_type": "file",
                        "thumbnail_url": file_data.get("thumbnailUrl"),
                    },
                    "acl": self.extract_acl(project_id, project_name),
                    "source_url": f"https://www.figma.com/file/{file_key}",
                    "timestamp": last_modified or file_data.get("lastModified"),
                }

                # Fetch and yield comments
                comments = self._fetch_file_comments(file_key)
                for comment in comments:
                    yield {
                        "source_id": f"figma_comment_{comment['id']}",
                        "source_type": "figma",
                        "title": f"Comment on {file_name}",
                        "content": comment.get("message", ""),
                        "metadata": {
                            "connector_id": self.connector.id,
                            "file_key": file_key,
                            "file_name": file_name,
                            "project_id": project_id,
                            "project_name": project_name,
                            "team_id": self.team_id,
                            "content_type": "comment",
                            "author": comment.get("user", {}).get("handle"),
                        },
                        "acl": self.extract_acl(project_id, project_name),
                        "source_url": f"https://www.figma.com/file/{file_key}",
                        "timestamp": comment.get("created_at"),
                    }

                file_count += 1
                synced_files.add(file_key)

    def _format_file_content(
        self,
        file_data: dict[str, Any],
        text_content: str,
    ) -> str:
        """Format file metadata and content as searchable text.

        Args:
            file_data: Full file data from API
            text_content: Extracted text from document

        Returns:
            Formatted string
        """
        parts = [
            f"Figma File: {file_data.get('name', 'Untitled')}",
            f"Version: {file_data.get('version', 'N/A')}",
        ]

        if text_content:
            parts.append(f"\nContent:\n{text_content}")

        return "\n".join(parts)

    def extract_acl(
        self,
        project_id: str,
        project_name: str,
    ) -> dict[str, Any]:
        """Extract ACL metadata from project.

        Args:
            project_id: Figma project ID
            project_name: Project name

        Returns:
            ACL dict with access_level and team_id
        """
        from src.connectors.figma.acl import normalize_figma_acl

        # Note: Member fetching is expensive, done separately in ACL module
        return normalize_figma_acl(
            project_id=project_id,
            project_name=project_name,
            team_id=self.team_id,
            members=[],
        )
