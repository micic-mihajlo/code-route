"""
Code Route Git - Git operations and GitHub integration.

Provides async Git operations for status, diff, commit,
branch management, and PR creation via GitHub CLI.
"""

from .operations import (
    GitOperations,
    GitStatus,
    GitDiff,
    GitCommit,
    GitBranch,
    GitError,
)
from .github import (
    GitHubOperations,
    PullRequest,
    Issue,
)

__all__ = [
    # Git operations
    "GitOperations",
    "GitStatus",
    "GitDiff",
    "GitCommit",
    "GitBranch",
    "GitError",
    # GitHub operations
    "GitHubOperations",
    "PullRequest",
    "Issue",
]
