"""
Git operations for Code Route.

Provides async wrappers around git commands with
structured output parsing.
"""

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class GitError(Exception):
    """Git operation error."""
    def __init__(self, message: str, command: str = "", stderr: str = ""):
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class FileStatus(Enum):
    """Git file status codes."""
    MODIFIED = "M"
    ADDED = "A"
    DELETED = "D"
    RENAMED = "R"
    COPIED = "C"
    UNTRACKED = "?"
    IGNORED = "!"
    UNMERGED = "U"


@dataclass
class StatusFile:
    """A file in git status."""
    path: str
    status: FileStatus
    staged: bool = False
    old_path: Optional[str] = None  # For renames


@dataclass
class GitStatus:
    """Git repository status."""
    branch: str
    ahead: int = 0
    behind: int = 0
    staged: List[StatusFile] = field(default_factory=list)
    unstaged: List[StatusFile] = field(default_factory=list)
    untracked: List[StatusFile] = field(default_factory=list)
    has_conflicts: bool = False

    @property
    def is_clean(self) -> bool:
        """Check if working directory is clean."""
        return not (self.staged or self.unstaged or self.untracked)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.staged or self.unstaged)


@dataclass
class DiffHunk:
    """A hunk in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: List[str]


@dataclass
class FileDiff:
    """Diff for a single file."""
    path: str
    old_path: Optional[str] = None
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    hunks: List[DiffHunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


@dataclass
class GitDiff:
    """Git diff result."""
    files: List[FileDiff]
    total_additions: int = 0
    total_deletions: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class GitCommit:
    """A git commit."""
    hash: str
    short_hash: str
    author: str
    email: str
    date: str
    subject: str
    body: str = ""


@dataclass
class GitBranch:
    """A git branch."""
    name: str
    is_current: bool = False
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0


class GitOperations:
    """
    Async Git operations.

    Provides high-level methods for common git operations
    with structured output parsing.

    Usage:
        git = GitOperations(repo_path="/my/repo")

        status = await git.status()
        print(f"On branch: {status.branch}")

        diff = await git.diff()
        print(f"Changed files: {diff.file_count}")
    """

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize Git operations.

        Args:
            repo_path: Path to git repository (default: cwd)
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    async def _run(
        self,
        *args: str,
        check: bool = True,
    ) -> Tuple[str, str, int]:
        """
        Run a git command.

        Args:
            *args: Command arguments
            check: Raise on non-zero exit

        Returns:
            Tuple of (stdout, stderr, returncode)
        """
        cmd = ["git", "-C", str(self.repo_path)] + list(args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        if check and proc.returncode != 0:
            raise GitError(
                f"Git command failed: {' '.join(args)}",
                command=" ".join(cmd),
                stderr=stderr_str,
            )

        return stdout_str, stderr_str, proc.returncode

    async def is_repo(self) -> bool:
        """Check if path is a git repository."""
        try:
            _, _, code = await self._run("rev-parse", "--git-dir", check=False)
            return code == 0
        except Exception:
            return False

    async def status(self) -> GitStatus:
        """
        Get repository status.

        Returns:
            GitStatus with branch info and file lists
        """
        # Get branch and tracking info
        stdout, _, _ = await self._run("status", "--porcelain=v2", "--branch")

        branch = ""
        ahead = 0
        behind = 0
        staged = []
        unstaged = []
        untracked = []
        has_conflicts = False

        for line in stdout.split("\n"):
            if not line:
                continue

            if line.startswith("# branch.head"):
                branch = line.split()[-1]
            elif line.startswith("# branch.ab"):
                parts = line.split()
                for part in parts[2:]:
                    if part.startswith("+"):
                        ahead = int(part[1:])
                    elif part.startswith("-"):
                        behind = int(part[1:])
            elif line.startswith("1 ") or line.startswith("2 "):
                # Changed entry
                parts = line.split("\t")
                info = parts[0].split()
                xy = info[1] if len(info) > 1 else ".."

                path = parts[-1] if len(parts) > 1 else info[-1]
                old_path = parts[-2] if line.startswith("2 ") and len(parts) > 2 else None

                x, y = xy[0], xy[1] if len(xy) > 1 else "."

                if x != ".":
                    status = self._parse_status(x)
                    staged.append(StatusFile(
                        path=path,
                        status=status,
                        staged=True,
                        old_path=old_path,
                    ))

                if y != ".":
                    status = self._parse_status(y)
                    unstaged.append(StatusFile(
                        path=path,
                        status=status,
                        staged=False,
                    ))
            elif line.startswith("? "):
                path = line[2:]
                untracked.append(StatusFile(
                    path=path,
                    status=FileStatus.UNTRACKED,
                    staged=False,
                ))
            elif line.startswith("u "):
                has_conflicts = True

        return GitStatus(
            branch=branch,
            ahead=ahead,
            behind=behind,
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
            has_conflicts=has_conflicts,
        )

    def _parse_status(self, code: str) -> FileStatus:
        """Parse a status code."""
        mapping = {
            "M": FileStatus.MODIFIED,
            "A": FileStatus.ADDED,
            "D": FileStatus.DELETED,
            "R": FileStatus.RENAMED,
            "C": FileStatus.COPIED,
            "?": FileStatus.UNTRACKED,
            "!": FileStatus.IGNORED,
            "U": FileStatus.UNMERGED,
        }
        return mapping.get(code, FileStatus.MODIFIED)

    async def diff(
        self,
        staged: bool = False,
        path: Optional[str] = None,
        base: Optional[str] = None,
    ) -> GitDiff:
        """
        Get diff of changes.

        Args:
            staged: Diff staged changes only
            path: Limit to specific path
            base: Diff against specific commit/branch

        Returns:
            GitDiff with file changes
        """
        args = ["diff", "--numstat"]

        if staged:
            args.append("--staged")
        if base:
            args.append(base)
        if path:
            args.extend(["--", path])

        stdout, _, _ = await self._run(*args)

        files = []
        total_add = 0
        total_del = 0

        for line in stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) >= 3:
                add = int(parts[0]) if parts[0] != "-" else 0
                delete = int(parts[1]) if parts[1] != "-" else 0
                filepath = parts[2]

                files.append(FileDiff(
                    path=filepath,
                    additions=add,
                    deletions=delete,
                    is_binary=(parts[0] == "-"),
                ))
                total_add += add
                total_del += delete

        return GitDiff(
            files=files,
            total_additions=total_add,
            total_deletions=total_del,
        )

    async def log(
        self,
        count: int = 10,
        branch: Optional[str] = None,
        path: Optional[str] = None,
    ) -> List[GitCommit]:
        """
        Get commit log.

        Args:
            count: Number of commits
            branch: Branch to log
            path: Limit to path

        Returns:
            List of commits
        """
        # Use a format that's easy to parse
        format_str = "%H%x00%h%x00%an%x00%ae%x00%ai%x00%s%x00%b%x1e"

        args = ["log", f"-{count}", f"--format={format_str}"]
        if branch:
            args.append(branch)
        if path:
            args.extend(["--", path])

        stdout, _, _ = await self._run(*args)

        commits = []
        for entry in stdout.split("\x1e"):
            entry = entry.strip()
            if not entry:
                continue

            parts = entry.split("\x00")
            if len(parts) >= 6:
                commits.append(GitCommit(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    email=parts[3],
                    date=parts[4],
                    subject=parts[5],
                    body=parts[6] if len(parts) > 6 else "",
                ))

        return commits

    async def branches(self, all_branches: bool = False) -> List[GitBranch]:
        """
        List branches.

        Args:
            all_branches: Include remote branches

        Returns:
            List of branches
        """
        args = ["branch", "-vv"]
        if all_branches:
            args.append("-a")

        stdout, _, _ = await self._run(*args)

        branches = []
        for line in stdout.split("\n"):
            if not line.strip():
                continue

            is_current = line.startswith("*")
            line = line[2:] if is_current else line

            parts = line.split()
            if not parts:
                continue

            name = parts[0]
            upstream = None
            ahead = 0
            behind = 0

            # Parse tracking info [origin/main: ahead 1, behind 2]
            tracking_match = re.search(r"\[([^\]]+)\]", line)
            if tracking_match:
                tracking = tracking_match.group(1)
                if ":" in tracking:
                    upstream, info = tracking.split(":", 1)
                    upstream = upstream.strip()

                    ahead_match = re.search(r"ahead (\d+)", info)
                    if ahead_match:
                        ahead = int(ahead_match.group(1))

                    behind_match = re.search(r"behind (\d+)", info)
                    if behind_match:
                        behind = int(behind_match.group(1))
                else:
                    upstream = tracking.strip()

            branches.append(GitBranch(
                name=name,
                is_current=is_current,
                upstream=upstream,
                ahead=ahead,
                behind=behind,
            ))

        return branches

    async def checkout(
        self,
        target: str,
        create: bool = False,
    ) -> None:
        """
        Checkout a branch or commit.

        Args:
            target: Branch name or commit hash
            create: Create new branch
        """
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(target)

        await self._run(*args)

    async def add(self, *paths: str, all_files: bool = False) -> None:
        """
        Stage files for commit.

        Args:
            *paths: Paths to add
            all_files: Add all changes
        """
        args = ["add"]
        if all_files:
            args.append("-A")
        else:
            args.extend(paths)

        await self._run(*args)

    async def commit(
        self,
        message: str,
        amend: bool = False,
        allow_empty: bool = False,
    ) -> GitCommit:
        """
        Create a commit.

        Args:
            message: Commit message
            amend: Amend previous commit
            allow_empty: Allow empty commit

        Returns:
            The created commit
        """
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        if allow_empty:
            args.append("--allow-empty")

        await self._run(*args)

        # Get the commit we just made
        commits = await self.log(count=1)
        return commits[0] if commits else GitCommit(
            hash="",
            short_hash="",
            author="",
            email="",
            date="",
            subject=message,
        )

    async def push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        set_upstream: bool = False,
        force: bool = False,
    ) -> None:
        """
        Push commits to remote.

        Args:
            remote: Remote name
            branch: Branch to push
            set_upstream: Set upstream tracking
            force: Force push
        """
        args = ["push"]
        if set_upstream:
            args.append("-u")
        if force:
            args.append("--force-with-lease")

        args.append(remote)
        if branch:
            args.append(branch)

        await self._run(*args)

    async def pull(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        rebase: bool = False,
    ) -> None:
        """
        Pull changes from remote.

        Args:
            remote: Remote name
            branch: Branch to pull
            rebase: Rebase instead of merge
        """
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        args.append(remote)
        if branch:
            args.append(branch)

        await self._run(*args)

    async def stash(
        self,
        message: Optional[str] = None,
        include_untracked: bool = False,
    ) -> None:
        """
        Stash changes.

        Args:
            message: Stash message
            include_untracked: Include untracked files
        """
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        if include_untracked:
            args.append("-u")

        await self._run(*args)

    async def stash_pop(self, index: int = 0) -> None:
        """Pop a stash."""
        await self._run("stash", "pop", f"stash@{{{index}}}")

    async def reset(
        self,
        target: str = "HEAD",
        hard: bool = False,
        soft: bool = False,
    ) -> None:
        """
        Reset to a commit.

        Args:
            target: Commit to reset to
            hard: Hard reset (discard changes)
            soft: Soft reset (keep changes staged)
        """
        args = ["reset"]
        if hard:
            args.append("--hard")
        elif soft:
            args.append("--soft")
        args.append(target)

        await self._run(*args)

    async def current_branch(self) -> str:
        """Get current branch name."""
        stdout, _, _ = await self._run("rev-parse", "--abbrev-ref", "HEAD")
        return stdout.strip()

    async def root_dir(self) -> Path:
        """Get repository root directory."""
        stdout, _, _ = await self._run("rev-parse", "--show-toplevel")
        return Path(stdout.strip())
