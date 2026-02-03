"""
GitHub operations via gh CLI.

Provides async wrappers around GitHub CLI for
pull requests, issues, and repository operations.
"""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class GitHubError(Exception):
    """GitHub operation error."""
    def __init__(self, message: str, command: str = "", stderr: str = ""):
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class PRState(Enum):
    """Pull request state."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class IssueState(Enum):
    """Issue state."""
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class PullRequest:
    """A GitHub pull request."""
    number: int
    title: str
    body: str = ""
    state: PRState = PRState.OPEN
    url: str = ""
    head_branch: str = ""
    base_branch: str = ""
    author: str = ""
    labels: List[str] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    is_draft: bool = False
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    mergeable: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Issue:
    """A GitHub issue."""
    number: int
    title: str
    body: str = ""
    state: IssueState = IssueState.OPEN
    url: str = ""
    author: str = ""
    labels: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Repository:
    """A GitHub repository."""
    name: str
    full_name: str
    description: str = ""
    url: str = ""
    default_branch: str = "main"
    is_private: bool = False
    is_fork: bool = False


class GitHubOperations:
    """
    GitHub operations via gh CLI.

    Provides high-level methods for GitHub operations
    using the official GitHub CLI.

    Requires: gh CLI installed and authenticated

    Usage:
        gh = GitHubOperations(repo_path="/my/repo")

        # Create a PR
        pr = await gh.create_pr(
            title="Add feature",
            body="Description here",
            base="main",
        )
        print(f"Created PR #{pr.number}: {pr.url}")

        # List issues
        issues = await gh.list_issues(state="open")
    """

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize GitHub operations.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    async def _run(
        self,
        *args: str,
        check: bool = True,
        json_output: bool = False,
    ) -> Tuple[str, str, int]:
        """
        Run a gh command.

        Args:
            *args: Command arguments
            check: Raise on non-zero exit
            json_output: Parse output as JSON

        Returns:
            Tuple of (stdout, stderr, returncode)
        """
        cmd = ["gh"] + list(args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.repo_path),
        )

        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        if check and proc.returncode != 0:
            raise GitHubError(
                f"GitHub CLI command failed: {' '.join(args)}",
                command=" ".join(cmd),
                stderr=stderr_str,
            )

        return stdout_str, stderr_str, proc.returncode

    async def is_authenticated(self) -> bool:
        """Check if gh CLI is authenticated."""
        try:
            _, _, code = await self._run("auth", "status", check=False)
            return code == 0
        except Exception:
            return False

    async def get_repo(self) -> Optional[Repository]:
        """
        Get current repository info.

        Returns:
            Repository info or None
        """
        try:
            stdout, _, _ = await self._run(
                "repo", "view", "--json",
                "name,nameWithOwner,description,url,defaultBranchRef,isPrivate,isFork",
            )
            data = json.loads(stdout)

            return Repository(
                name=data.get("name", ""),
                full_name=data.get("nameWithOwner", ""),
                description=data.get("description", ""),
                url=data.get("url", ""),
                default_branch=data.get("defaultBranchRef", {}).get("name", "main"),
                is_private=data.get("isPrivate", False),
                is_fork=data.get("isFork", False),
            )
        except Exception:
            return None

    # === Pull Request Operations ===

    async def create_pr(
        self,
        title: str,
        body: str = "",
        base: Optional[str] = None,
        head: Optional[str] = None,
        draft: bool = False,
        labels: Optional[List[str]] = None,
        reviewers: Optional[List[str]] = None,
    ) -> PullRequest:
        """
        Create a pull request.

        Args:
            title: PR title
            body: PR body/description
            base: Base branch (default: repo default)
            head: Head branch (default: current branch)
            draft: Create as draft
            labels: Labels to add
            reviewers: Reviewers to request

        Returns:
            Created PullRequest
        """
        args = ["pr", "create", "--title", title]

        if body:
            args.extend(["--body", body])
        if base:
            args.extend(["--base", base])
        if head:
            args.extend(["--head", head])
        if draft:
            args.append("--draft")
        if labels:
            args.extend(["--label", ",".join(labels)])
        if reviewers:
            args.extend(["--reviewer", ",".join(reviewers)])

        stdout, _, _ = await self._run(*args)

        # Get PR URL from output
        url = stdout.strip()

        # Fetch full PR details
        return await self.get_pr(url=url)

    async def get_pr(
        self,
        number: Optional[int] = None,
        url: Optional[str] = None,
    ) -> PullRequest:
        """
        Get pull request details.

        Args:
            number: PR number
            url: PR URL

        Returns:
            PullRequest details
        """
        args = ["pr", "view"]

        if number:
            args.append(str(number))
        elif url:
            args.append(url)

        args.extend([
            "--json",
            "number,title,body,state,url,headRefName,baseRefName,"
            "author,labels,reviewRequests,isDraft,additions,deletions,"
            "changedFiles,mergeable,createdAt,updatedAt"
        ])

        stdout, _, _ = await self._run(*args)
        data = json.loads(stdout)

        return PullRequest(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=PRState(data.get("state", "open").lower()),
            url=data.get("url", ""),
            head_branch=data.get("headRefName", ""),
            base_branch=data.get("baseRefName", ""),
            author=data.get("author", {}).get("login", ""),
            labels=[l.get("name", "") for l in data.get("labels", [])],
            reviewers=[r.get("login", "") for r in data.get("reviewRequests", [])],
            is_draft=data.get("isDraft", False),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changedFiles", 0),
            mergeable=data.get("mergeable", "") != "CONFLICTING",
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    async def list_prs(
        self,
        state: str = "open",
        limit: int = 30,
        author: Optional[str] = None,
        base: Optional[str] = None,
    ) -> List[PullRequest]:
        """
        List pull requests.

        Args:
            state: PR state (open, closed, merged, all)
            limit: Maximum number to return
            author: Filter by author
            base: Filter by base branch

        Returns:
            List of PullRequests
        """
        args = [
            "pr", "list",
            "--state", state,
            "--limit", str(limit),
            "--json",
            "number,title,state,url,headRefName,baseRefName,author,isDraft,createdAt"
        ]

        if author:
            args.extend(["--author", author])
        if base:
            args.extend(["--base", base])

        stdout, _, _ = await self._run(*args)
        data = json.loads(stdout)

        return [
            PullRequest(
                number=pr.get("number", 0),
                title=pr.get("title", ""),
                state=PRState(pr.get("state", "open").lower()),
                url=pr.get("url", ""),
                head_branch=pr.get("headRefName", ""),
                base_branch=pr.get("baseRefName", ""),
                author=pr.get("author", {}).get("login", ""),
                is_draft=pr.get("isDraft", False),
                created_at=pr.get("createdAt", ""),
            )
            for pr in data
        ]

    async def merge_pr(
        self,
        number: int,
        method: str = "merge",
        delete_branch: bool = False,
    ) -> bool:
        """
        Merge a pull request.

        Args:
            number: PR number
            method: Merge method (merge, squash, rebase)
            delete_branch: Delete branch after merge

        Returns:
            True if merged successfully
        """
        args = ["pr", "merge", str(number), f"--{method}"]

        if delete_branch:
            args.append("--delete-branch")

        try:
            await self._run(*args)
            return True
        except GitHubError:
            return False

    async def close_pr(self, number: int, comment: Optional[str] = None) -> bool:
        """Close a pull request."""
        args = ["pr", "close", str(number)]
        if comment:
            args.extend(["--comment", comment])

        try:
            await self._run(*args)
            return True
        except GitHubError:
            return False

    async def pr_checkout(self, number: int) -> None:
        """Checkout a PR's branch locally."""
        await self._run("pr", "checkout", str(number))

    async def pr_diff(self, number: int) -> str:
        """Get PR diff."""
        stdout, _, _ = await self._run("pr", "diff", str(number))
        return stdout

    async def pr_review(
        self,
        number: int,
        approve: bool = False,
        request_changes: bool = False,
        comment: Optional[str] = None,
    ) -> None:
        """
        Review a pull request.

        Args:
            number: PR number
            approve: Approve the PR
            request_changes: Request changes
            comment: Review comment
        """
        args = ["pr", "review", str(number)]

        if approve:
            args.append("--approve")
        elif request_changes:
            args.append("--request-changes")
        else:
            args.append("--comment")

        if comment:
            args.extend(["--body", comment])

        await self._run(*args)

    # === Issue Operations ===

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Issue:
        """
        Create an issue.

        Args:
            title: Issue title
            body: Issue body
            labels: Labels to add
            assignees: Users to assign

        Returns:
            Created Issue
        """
        args = ["issue", "create", "--title", title]

        if body:
            args.extend(["--body", body])
        if labels:
            args.extend(["--label", ",".join(labels)])
        if assignees:
            args.extend(["--assignee", ",".join(assignees)])

        stdout, _, _ = await self._run(*args)
        url = stdout.strip()

        # Extract issue number from URL
        number = int(url.split("/")[-1])
        return await self.get_issue(number)

    async def get_issue(self, number: int) -> Issue:
        """Get issue details."""
        stdout, _, _ = await self._run(
            "issue", "view", str(number),
            "--json",
            "number,title,body,state,url,author,labels,assignees,createdAt,updatedAt"
        )
        data = json.loads(stdout)

        return Issue(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=IssueState(data.get("state", "open").lower()),
            url=data.get("url", ""),
            author=data.get("author", {}).get("login", ""),
            labels=[l.get("name", "") for l in data.get("labels", [])],
            assignees=[a.get("login", "") for a in data.get("assignees", [])],
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    async def list_issues(
        self,
        state: str = "open",
        limit: int = 30,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
    ) -> List[Issue]:
        """
        List issues.

        Args:
            state: Issue state (open, closed, all)
            limit: Maximum number
            labels: Filter by labels
            assignee: Filter by assignee

        Returns:
            List of Issues
        """
        args = [
            "issue", "list",
            "--state", state,
            "--limit", str(limit),
            "--json",
            "number,title,state,url,author,labels,createdAt"
        ]

        if labels:
            args.extend(["--label", ",".join(labels)])
        if assignee:
            args.extend(["--assignee", assignee])

        stdout, _, _ = await self._run(*args)
        data = json.loads(stdout)

        return [
            Issue(
                number=issue.get("number", 0),
                title=issue.get("title", ""),
                state=IssueState(issue.get("state", "open").lower()),
                url=issue.get("url", ""),
                author=issue.get("author", {}).get("login", ""),
                labels=[l.get("name", "") for l in issue.get("labels", [])],
                created_at=issue.get("createdAt", ""),
            )
            for issue in data
        ]

    async def close_issue(
        self,
        number: int,
        comment: Optional[str] = None,
        reason: str = "completed",
    ) -> bool:
        """
        Close an issue.

        Args:
            number: Issue number
            comment: Closing comment
            reason: Close reason (completed, not_planned)

        Returns:
            True if closed successfully
        """
        args = ["issue", "close", str(number), "--reason", reason]

        if comment:
            args.extend(["--comment", comment])

        try:
            await self._run(*args)
            return True
        except GitHubError:
            return False

    async def comment_issue(self, number: int, body: str) -> None:
        """Add a comment to an issue."""
        await self._run("issue", "comment", str(number), "--body", body)

    # === Repository Operations ===

    async def clone(
        self,
        repo: str,
        directory: Optional[str] = None,
    ) -> Path:
        """
        Clone a repository.

        Args:
            repo: Repository (owner/name or URL)
            directory: Target directory

        Returns:
            Path to cloned repository
        """
        args = ["repo", "clone", repo]
        if directory:
            args.append(directory)

        await self._run(*args, check=True)

        # Return path
        if directory:
            return self.repo_path / directory
        else:
            # Extract repo name
            name = repo.split("/")[-1].replace(".git", "")
            return self.repo_path / name

    async def fork(
        self,
        repo: str,
        clone: bool = True,
    ) -> Repository:
        """
        Fork a repository.

        Args:
            repo: Repository to fork
            clone: Clone the fork locally

        Returns:
            Forked Repository
        """
        args = ["repo", "fork", repo]
        if clone:
            args.append("--clone")
        else:
            args.append("--clone=false")

        await self._run(*args)

        # Get fork info
        return await self.get_repo()

    async def sync_fork(self, branch: Optional[str] = None) -> None:
        """Sync fork with upstream."""
        args = ["repo", "sync"]
        if branch:
            args.extend(["--branch", branch])

        await self._run(*args)
