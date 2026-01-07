"""Jira connector implementation.

Fetches issues, comments, and projects from Jira Cloud instances.
Supports incremental sync using JQL queries with updated timestamps.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import requests

from src.connectors.sdk import (
    ConnectorBase,
    OAuth2Token,
    PageResult,
    rate_limit,
)
from src.models.connector import Connector

logger = logging.getLogger(__name__)


class JiraConnector(ConnectorBase):
    """Jira Cloud connector.
    
    Fetches:
    - Issues with fields (summary, description, status, assignee, reporter)
    - Comments on issues
    - Project metadata for ACL
    - User information for identity resolution
    
    OAuth Scopes Required:
    - read:jira-work - Read issues, projects, comments
    - read:jira-user - Read user information
    """

    RATE_LIMIT_CALLS = 10  # Jira Cloud: 10 requests per second
    RATE_LIMIT_PERIOD = 1  # seconds

    def __init__(self, connector: Connector):
        """Initialize Jira connector.
        
        Args:
            connector: Connector model instance with credentials and config
        """
        super().__init__(connector)
        self._oauth_token: Optional[OAuth2Token] = None
        self._users_cache: Dict[str, Dict[str, Any]] = {}
        self._projects_cache: Dict[str, Dict[str, Any]] = {}
        
        # Get Jira instance URL from config
        self.instance_url = self.connector.config_json.get("instance_url", "")
        if not self.instance_url:
            raise ValueError("Jira instance_url is required in connector config")
        
        # Remove trailing slash
        self.instance_url = self.instance_url.rstrip("/")
        self.api_base = f"{self.instance_url}/rest/api/3"

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authorization."""
        if self._oauth_token is None:
            # Load token from connector credentials
            # TODO: Implement credentials_encrypted decryption
            # For now, assume credentials is available as property
            creds = getattr(self.connector, 'credentials', {})
            if creds:
                self._oauth_token = OAuth2Token(
                    access_token=creds["access_token"],
                    token_type=creds.get("token_type", "Bearer"),
                    expires_in=creds.get("expires_in", 3600),
                    refresh_token=creds.get("refresh_token"),
                    scope=creds.get("scope", ""),
                    expires_at=creds.get("expires_at", datetime.now().timestamp() + 3600),
                )

        return {
            "Authorization": f"Bearer {self._oauth_token.access_token}" if self._oauth_token else "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_issues_page(
        self,
        jql: str = "",
        start_at: int = 0,
        max_results: int = 50,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Fetch page of issues from Jira API.
        
        Args:
            jql: JQL query string for filtering
            start_at: Pagination offset
            max_results: Number of issues per page (max 100)
            fields: List of fields to include (default: all)
            
        Returns:
            API response with issues list and pagination info
        """
        url = f"{self.api_base}/search"
        
        if fields is None:
            fields = [
                "summary",
                "description",
                "status",
                "assignee",
                "reporter",
                "created",
                "updated",
                "issuetype",
                "priority",
                "project",
                "comment",
                "security",
            ]
        
        params = {
            "jql": jql or "ORDER BY updated DESC",
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields),
            "expand": "renderedFields",  # Get rendered HTML for rich text
        }

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_project(self, project_key: str) -> Dict[str, Any]:
        """Fetch project metadata from Jira API.
        
        Args:
            project_key: Jira project key (e.g., "PROJ")
            
        Returns:
            Project metadata including roles
        """
        url = f"{self.api_base}/project/{project_key}"
        
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        data = response.json()

        return data

    @rate_limit(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD, handle_429=True)
    def _fetch_users_page(
        self, start_at: int = 0, max_results: int = 50
    ) -> Dict[str, Any]:
        """Fetch page of users from Jira API.
        
        Args:
            start_at: Pagination offset
            max_results: Number of users per page
            
        Returns:
            List of users
        """
        url = f"{self.api_base}/users/search"
        params = {
            "startAt": start_at,
            "maxResults": max_results,
        }

        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        return data

    def _load_projects_cache(self) -> None:
        """Load all projects into cache for ACL metadata."""
        logger.info("Loading Jira projects into cache")
        
        # Fetch all projects
        url = f"{self.api_base}/project"
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        projects = response.json()
        
        for project in projects:
            project_key = project.get("key")
            if project_key:
                self._projects_cache[project_key] = project
        
        logger.info(f"Loaded {len(self._projects_cache)} projects into cache")

    def _load_users_cache(self) -> None:
        """Load all users into cache for identity resolution."""
        logger.info("Loading Jira users into cache")
        
        start_at = 0
        max_results = 50
        
        while True:
            users_data = self._fetch_users_page(start_at=start_at, max_results=max_results)
            
            # Jira returns a list directly
            if not users_data:
                break
            
            for user in users_data:
                account_id = user.get("accountId")
                if account_id:
                    self._users_cache[account_id] = user
            
            # Check if there are more users
            if len(users_data) < max_results:
                break
            
            start_at += max_results
        
        logger.info(f"Loaded {len(self._users_cache)} users into cache")

    def sync(
        self,
        cursor_state: Optional[Dict[str, Any]] = None,
        max_issues: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Sync issues from Jira instance.
        
        Args:
            cursor_state: State from previous sync for incremental updates
            max_issues: Limit number of issues to sync (for testing)
            
        Yields:
            Document dicts with content, metadata, and acl_metadata
        """
        logger.info(f"Starting Jira sync for connector {self.connector.id}")

        # Load projects and users into cache
        self._load_projects_cache()
        self._load_users_cache()

        # Build JQL query for incremental sync
        jql_parts = []
        
        # Get last sync timestamp from cursor state
        last_sync_timestamp = None
        if cursor_state:
            last_sync_timestamp = cursor_state.get("last_sync_timestamp")
        
        if last_sync_timestamp:
            # Incremental sync: only fetch updated issues
            jql_parts.append(f'updated >= "{last_sync_timestamp}"')
        
        # Filter by projects if configured
        project_keys = self.connector.config_json.get("project_keys")
        if project_keys:
            projects_jql = ", ".join(f'"{key}"' for key in project_keys)
            jql_parts.append(f"project IN ({projects_jql})")
        
        # Order by updated for consistent pagination
        jql_parts.append("ORDER BY updated ASC")
        
        jql = " AND ".join(jql_parts) if jql_parts else "ORDER BY updated ASC"
        
        logger.info(f"Using JQL query: {jql}")

        # Fetch issues with offset-based pagination
        start_at = 0
        max_results = 50
        issues_processed = 0

        while True:
            if max_issues and issues_processed >= max_issues:
                break

            # Fetch page of issues
            issues_data = self._fetch_issues_page(
                jql=jql, start_at=start_at, max_results=max_results
            )

            issues = issues_data.get("issues", [])
            total = issues_data.get("total", 0)

            if not issues:
                break

            for issue in issues:
                if max_issues and issues_processed >= max_issues:
                    break

                # Extract issue details
                issue_key = issue.get("key")
                issue_id = issue.get("id")
                fields = issue.get("fields", {})

                summary = fields.get("summary", "")
                description = fields.get("description", "")
                status = fields.get("status", {}).get("name", "")
                issue_type = fields.get("issuetype", {}).get("name", "")
                priority = fields.get("priority", {}).get("name", "")
                created = fields.get("created")
                updated = fields.get("updated")

                # Get assignee and reporter
                assignee = fields.get("assignee")
                reporter = fields.get("reporter")

                # Get project info
                project = fields.get("project", {})
                project_key = project.get("key")
                project_name = project.get("name")

                # Build document content
                content_parts = [f"Issue: {issue_key} - {summary}"]
                if description:
                    content_parts.append(f"\nDescription: {description}")
                content_parts.append(f"\nStatus: {status}")
                content_parts.append(f"\nType: {issue_type}")
                if priority:
                    content_parts.append(f"\nPriority: {priority}")

                content = "\n".join(content_parts)

                # Build metadata
                metadata = {
                    "issue_key": issue_key,
                    "issue_id": issue_id,
                    "issue_type": issue_type,
                    "status": status,
                    "priority": priority,
                    "project_key": project_key,
                    "project_name": project_name,
                    "created": created,
                    "updated": updated,
                    "source_url": f"{self.instance_url}/browse/{issue_key}",
                }

                # Add assignee info
                if assignee:
                    assignee_id = assignee.get("accountId")
                    metadata["assignee_id"] = assignee_id
                    metadata["assignee_name"] = assignee.get("displayName")
                    metadata["assignee_email"] = assignee.get("emailAddress")

                # Add reporter info
                if reporter:
                    reporter_id = reporter.get("accountId")
                    metadata["reporter_id"] = reporter_id
                    metadata["reporter_name"] = reporter.get("displayName")
                    metadata["reporter_email"] = reporter.get("emailAddress")

                # Get security level
                security = fields.get("security")
                if security:
                    metadata["security_level"] = security.get("name")
                    metadata["security_level_id"] = security.get("id")

                # Extract ACL metadata
                acl_metadata = self.extract_acl(metadata)

                # Yield issue document
                document = {
                    "source_id": f"jira_{issue_key}",
                    "source_type": "jira",
                    "content": content,
                    "metadata": metadata,
                    "acl_metadata": acl_metadata,
                }
                yield document

                # Fetch and yield comments
                comments = fields.get("comment", {}).get("comments", [])
                for comment in comments:
                    comment_id = comment.get("id")
                    comment_body = comment.get("body", "")
                    comment_author = comment.get("author", {})
                    comment_created = comment.get("created")

                    if not comment_body:
                        continue

                    comment_content = f"Comment on {issue_key}: {comment_body}"

                    comment_metadata = {
                        "issue_key": issue_key,
                        "comment_id": comment_id,
                        "project_key": project_key,
                        "project_name": project_name,
                        "author_id": comment_author.get("accountId"),
                        "author_name": comment_author.get("displayName"),
                        "author_email": comment_author.get("emailAddress"),
                        "created": comment_created,
                        "source_url": f"{self.instance_url}/browse/{issue_key}?focusedCommentId={comment_id}",
                    }

                    # Comments inherit issue ACL
                    comment_acl = self.extract_acl(comment_metadata)

                    comment_document = {
                        "source_id": f"jira_{issue_key}_comment_{comment_id}",
                        "source_type": "jira",
                        "content": comment_content,
                        "metadata": comment_metadata,
                        "acl_metadata": comment_acl,
                    }
                    yield comment_document

                issues_processed += 1

            # Check if there are more issues
            if start_at + len(issues) >= total:
                break

            start_at += max_results

        # Update cursor state
        self._cursor_state = {
            "last_sync_timestamp": datetime.now().isoformat(),
        }

        logger.info(f"Jira sync complete: {issues_processed} issues processed")

    def fetch_page(
        self, page_cursor: Optional[str] = None, page_size: int = 50
    ) -> Dict[str, Any]:
        """Fetch a page of issues (for API compatibility).
        
        Args:
            page_cursor: Pagination cursor (startAt as string)
            page_size: Number of items per page
            
        Returns:
            Page of issues with cursor
        """
        start_at = int(page_cursor) if page_cursor else 0
        data = self._fetch_issues_page(start_at=start_at, max_results=page_size)
        
        issues = data.get("issues", [])
        total = data.get("total", 0)
        next_start_at = start_at + len(issues)
        
        return {
            "items": issues,
            "next_cursor": str(next_start_at) if next_start_at < total else None,
            "has_more": next_start_at < total,
        }

    def extract_acl(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract ACL metadata from document metadata.
        
        Args:
            metadata: Document metadata with project and security info
            
        Returns:
            ACL metadata with access control rules
        """
        project_key = metadata.get("project_key")
        security_level = metadata.get("security_level")
        security_level_id = metadata.get("security_level_id")

        acl = {
            "project_key": project_key,
            "connector_type": "jira",
        }

        if security_level:
            # Issue has security level - restricted access
            acl["access_level"] = "restricted"
            acl["security_level"] = security_level
            acl["security_level_id"] = security_level_id
            # TODO: Fetch users with security level access
            acl["allowed_users"] = []
        else:
            # No security level - project-level access
            acl["access_level"] = "project"
            acl["requires_project_role"] = True

        # Get project visibility from cache
        if project_key in self._projects_cache:
            project = self._projects_cache[project_key]
            # Check if project is public or private (simplified for MVP)
            acl["project_name"] = project.get("name")

        return acl
