"""GitHub connector for syncing repositories, issues, PRs, and files."""

import base64
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Optional

import requests

from src.connectors.sdk.base import ConnectorBase
from src.connectors.sdk.rate_limiter import rate_limit
from src.models.connector import Connector


class GitHubConnector(ConnectorBase):
    """GitHub connector for repositories, issues, PRs, and README files.

    Syncs:
    - Repository metadata
    - Issues and issue comments
    - Pull requests and PR comments
    - README files and important docs

    OAuth Scopes Required:
    - repo: Full access to repositories
    - read:org: Read organization membership
    - read:user: Read user profile data

    Rate Limits:
    - 5000 requests/hour for authenticated requests
    - Link header pagination with page/per_page

    ACL:
    - Public repositories: Anyone can read
    - Private repositories: Only collaborators with read+ permissions
    - Internal repositories: Organization members only
    """

    BASE_URL = "https://api.github.com"
    RATE_LIMIT_REQUESTS = 5000
    RATE_LIMIT_PERIOD = 3600  # 1 hour

    def __init__(self, connector: Connector):
        """Initialize GitHub connector.

        Args:
            connector: Connector model instance with GitHub config
        """
        super().__init__(connector)
        self.config = connector.config or {}
        self.organization = self.config.get("organization")
        self.repositories = self.config.get("repositories", [])
        self.user_cache: dict[str, dict[str, Any]] = {}
        self.repo_cache: dict[str, dict[str, Any]] = {}

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for GitHub API.

        Returns:
            Dict with Authorization header
        """
        credentials = getattr(self.connector, "credentials", {})
        access_token = credentials.get("access_token")

        if not access_token:
            raise ValueError("GitHub access token not found in connector credentials")

        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @rate_limit(requests=5000, period=3600)
    def _fetch_repos_page(
        self,
        page: int = 1,
        per_page: int = 30,
        since: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of repositories.

        Args:
            page: Page number (1-indexed)
            per_page: Results per page
            since: ISO timestamp for incremental sync

        Returns:
            List of repository dicts
        """
        headers = self._get_auth_headers()

        if self.organization:
            url = f"{self.BASE_URL}/orgs/{self.organization}/repos"
        else:
            url = f"{self.BASE_URL}/user/repos"

        params = {
            "page": page,
            "per_page": per_page,
            "sort": "updated",
            "direction": "desc",
            "type": "all",  # all, public, private
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        repos = response.json()

        # Filter by since timestamp if provided
        if since:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            repos = [
                r
                for r in repos
                if datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                > since_dt
            ]

        # Filter by repository list if provided
        if self.repositories:
            repos = [r for r in repos if r["name"] in self.repositories]

        return repos

    @rate_limit(requests=5000, period=3600)
    def _fetch_issues_page(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
        since: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of issues for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            page: Page number
            per_page: Results per page
            since: ISO timestamp for incremental sync

        Returns:
            List of issue dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"

        params = {
            "page": page,
            "per_page": per_page,
            "state": "all",
            "sort": "updated",
            "direction": "desc",
        }

        if since:
            params["since"] = since

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        issues = response.json()

        # Filter out pull requests (they appear in issues endpoint too)
        issues = [i for i in issues if "pull_request" not in i]

        return issues

    @rate_limit(requests=5000, period=3600)
    def _fetch_pulls_page(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
        since: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of pull requests for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            page: Page number
            per_page: Results per page
            since: ISO timestamp for incremental sync

        Returns:
            List of PR dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls"

        params = {
            "page": page,
            "per_page": per_page,
            "state": "all",
            "sort": "updated",
            "direction": "desc",
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        pulls = response.json()

        # Filter by since timestamp if provided
        if since:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            pulls = [
                p
                for p in pulls
                if datetime.fromisoformat(p["updated_at"].replace("Z", "+00:00"))
                > since_dt
            ]

        return pulls

    @rate_limit(requests=5000, period=3600)
    def _fetch_readme(
        self,
        owner: str,
        repo: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch README file for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            README dict or None if not found
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    @rate_limit(requests=5000, period=3600)
    def _fetch_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> list[dict[str, Any]]:
        """Fetch comments for an issue.

        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue number

        Returns:
            List of comment dicts
        """
        headers = self._get_auth_headers()
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{issue_number}/comments"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

    def _decode_content(self, content_base64: str) -> str:
        """Decode base64 content from GitHub API.

        Args:
            content_base64: Base64 encoded content

        Returns:
            Decoded UTF-8 string
        """
        try:
            decoded = base64.b64decode(content_base64)
            return decoded.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _load_repo_cache(self) -> None:
        """Load all repositories into cache."""
        page = 1
        while True:
            repos = self._fetch_repos_page(page=page, per_page=100)
            if not repos:
                break

            for repo in repos:
                self.repo_cache[repo["full_name"]] = repo

            page += 1

    def sync(
        self,
        cursor_state: Optional[dict[str, Any]] = None,
        max_repos: Optional[int] = None,
        max_issues_per_repo: Optional[int] = None,
        max_prs_per_repo: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """Sync repositories, issues, PRs, and READMEs from GitHub.

        Args:
            cursor_state: State from previous sync with last_updated, synced_repos
            max_repos: Maximum number of repositories to sync (for testing)
            max_issues_per_repo: Maximum issues per repo (for testing)
            max_prs_per_repo: Maximum PRs per repo (for testing)

        Yields:
            Document dicts with source_id, content, metadata, acl
        """
        since_timestamp = None
        synced_repos = set()

        if cursor_state:
            since_timestamp = cursor_state.get("last_updated")
            synced_repos = set(cursor_state.get("synced_repos", []))

        # Fetch repositories
        repo_count = 0
        page = 1

        while True:
            repos = self._fetch_repos_page(
                page=page,
                per_page=30,
                since=since_timestamp,
            )

            if not repos:
                break

            for repo in repos:
                if max_repos and repo_count >= max_repos:
                    return

                owner = repo["owner"]["login"]
                repo_name = repo["name"]
                full_name = repo["full_name"]

                # Skip if already synced in this session
                if full_name in synced_repos:
                    continue

                # Cache repo metadata
                self.repo_cache[full_name] = repo

                # Yield repository document
                yield {
                    "source_id": f"github_repo_{repo['id']}",
                    "source_type": "github",
                    "title": f"Repository: {full_name}",
                    "content": self._format_repo_content(repo),
                    "metadata": {
                        "connector_id": self.connector.id,
                        "repo_name": repo_name,
                        "owner": owner,
                        "full_name": full_name,
                        "repository": full_name,
                        "content_type": "repository",
                        "visibility": "public" if not repo["private"] else "private",
                        "default_branch": repo.get("default_branch"),
                        "language": repo.get("language"),
                        "topics": repo.get("topics", []),
                    },
                    "acl": self.extract_acl(repo),
                    "source_url": repo["html_url"],
                    "timestamp": repo["updated_at"],
                }

                # Fetch README
                readme = self._fetch_readme(owner, repo_name)
                if readme:
                    content = self._decode_content(readme["content"])
                    yield {
                        "source_id": f"github_readme_{repo['id']}",
                        "source_type": "github",
                        "title": f"README: {full_name}",
                        "content": content,
                        "metadata": {
                            "connector_id": self.connector.id,
                            "repo_name": repo_name,
                            "owner": owner,
                            "full_name": full_name,
                            "repository": full_name,
                            "content_type": "readme",
                            "file_path": readme["path"],
                        },
                        "acl": self.extract_acl(repo),
                        "source_url": readme["html_url"],
                        "timestamp": repo["updated_at"],
                    }

                # Fetch issues
                issue_count = 0
                issue_page = 1
                while True:
                    if max_issues_per_repo and issue_count >= max_issues_per_repo:
                        break

                    issues = self._fetch_issues_page(
                        owner=owner,
                        repo=repo_name,
                        page=issue_page,
                        per_page=30,
                        since=since_timestamp,
                    )

                    if not issues:
                        break

                    for issue in issues:
                        if max_issues_per_repo and issue_count >= max_issues_per_repo:
                            break

                        # Yield issue document
                        yield {
                            "source_id": f"github_issue_{issue['id']}",
                            "source_type": "github",
                            "title": f"Issue #{issue['number']}: {issue['title']}",
                            "content": self._format_issue_content(issue),
                            "metadata": {
                                "connector_id": self.connector.id,
                                "repo_name": repo_name,
                                "owner": owner,
                                "full_name": full_name,
                                "repository": full_name,
                                "content_type": "issue",
                                "issue_number": issue["number"],
                                "state": issue["state"],
                                "author": issue["user"]["login"],
                                "labels": [label["name"] for label in issue.get("labels", [])],
                            },
                            "acl": self.extract_acl(repo),
                            "source_url": issue["html_url"],
                            "timestamp": issue["updated_at"],
                        }

                        # Fetch comments if present
                        if issue.get("comments", 0) > 0:
                            comments = self._fetch_issue_comments(
                                owner, repo_name, issue["number"]
                            )
                            for comment in comments:
                                yield {
                                    "source_id": f"github_issue_comment_{comment['id']}",
                                    "source_type": "github",
                                    "title": f"Comment on Issue #{issue['number']}",
                                    "content": comment.get("body", ""),
                                    "metadata": {
                                        "connector_id": self.connector.id,
                                        "repo_name": repo_name,
                                        "owner": owner,
                                        "full_name": full_name,
                                        "repository": full_name,
                                        "content_type": "issue_comment",
                                        "issue_number": issue["number"],
                                        "author": comment["user"]["login"],
                                    },
                                    "acl": self.extract_acl(repo),
                                    "source_url": comment["html_url"],
                                    "timestamp": comment["updated_at"],
                                }

                        issue_count += 1

                    issue_page += 1

                # Fetch pull requests
                pr_count = 0
                pr_page = 1
                while True:
                    if max_prs_per_repo and pr_count >= max_prs_per_repo:
                        break

                    pulls = self._fetch_pulls_page(
                        owner=owner,
                        repo=repo_name,
                        page=pr_page,
                        per_page=30,
                        since=since_timestamp,
                    )

                    if not pulls:
                        break

                    for pr in pulls:
                        if max_prs_per_repo and pr_count >= max_prs_per_repo:
                            break

                        # Yield PR document
                        yield {
                            "source_id": f"github_pr_{pr['id']}",
                            "source_type": "github",
                            "title": f"PR #{pr['number']}: {pr['title']}",
                            "content": self._format_pr_content(pr),
                            "metadata": {
                                "connector_id": self.connector.id,
                                "repo_name": repo_name,
                                "owner": owner,
                                "full_name": full_name,
                                "repository": full_name,
                                "content_type": "pull_request",
                                "pr_number": pr["number"],
                                "state": pr["state"],
                                "author": pr["user"]["login"],
                                "base_branch": pr["base"]["ref"],
                                "head_branch": pr["head"]["ref"],
                            },
                            "acl": self.extract_acl(repo),
                            "source_url": pr["html_url"],
                            "timestamp": pr["updated_at"],
                        }

                        pr_count += 1

                    pr_page += 1

                repo_count += 1
                synced_repos.add(full_name)

            page += 1

    def _format_repo_content(self, repo: dict[str, Any]) -> str:
        """Format repository metadata as searchable content.

        Args:
            repo: Repository dict from API

        Returns:
            Formatted string
        """
        parts = [
            f"Repository: {repo['full_name']}",
            f"Description: {repo.get('description', 'No description')}",
            f"Language: {repo.get('language', 'N/A')}",
            f"Stars: {repo.get('stargazers_count', 0)}",
            f"Forks: {repo.get('forks_count', 0)}",
        ]

        if repo.get("topics"):
            parts.append(f"Topics: {', '.join(repo['topics'])}")

        return "\n".join(parts)

    def _format_issue_content(self, issue: dict[str, Any]) -> str:
        """Format issue as searchable content.

        Args:
            issue: Issue dict from API

        Returns:
            Formatted string
        """
        parts = [
            f"Issue #{issue['number']}: {issue['title']}",
            f"Author: {issue['user']['login']}",
            f"State: {issue['state']}",
        ]

        if issue.get("labels"):
            labels = [label["name"] for label in issue["labels"]]
            parts.append(f"Labels: {', '.join(labels)}")

        body = issue.get("body", "")
        if body:
            parts.append(f"\n{body}")

        return "\n".join(parts)

    def _format_pr_content(self, pr: dict[str, Any]) -> str:
        """Format pull request as searchable content.

        Args:
            pr: PR dict from API

        Returns:
            Formatted string
        """
        parts = [
            f"Pull Request #{pr['number']}: {pr['title']}",
            f"Author: {pr['user']['login']}",
            f"State: {pr['state']}",
            f"Base: {pr['base']['ref']} ← Head: {pr['head']['ref']}",
        ]

        body = pr.get("body", "")
        if body:
            parts.append(f"\n{body}")

        return "\n".join(parts)

    def extract_acl(self, repo: dict[str, Any]) -> dict[str, Any]:
        """Extract ACL metadata from repository.

        Args:
            repo: Repository dict from API

        Returns:
            ACL dict with access_level and allowed_users
        """
        from src.connectors.github.acl import normalize_github_acl

        visibility = "public" if not repo["private"] else "private"
        owner = repo["owner"]["login"]
        repo_name = repo["name"]

        # Note: Collaborator fetching is expensive, done separately in ACL module
        return normalize_github_acl(
            visibility=visibility,
            owner=owner,
            repo_name=repo_name,
            collaborators=[],
        )
