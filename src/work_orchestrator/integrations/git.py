"""Git subprocess wrappers for worktree and branch operations."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Raised when a git command fails."""


@dataclass
class WorktreeInfo:
    path: str
    branch: str
    head: str
    is_bare: bool = False


def run_git(args: list[str], cwd: str | Path | None = None) -> str:
    """Run a git command and return stdout. Raises GitError on failure."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr.strip()}") from e


def worktree_add(
    repo_path: str | Path,
    worktree_path: str | Path,
    branch: str,
    base_branch: str = "main",
    create_branch: bool = True,
) -> str:
    """Create a new git worktree."""
    args = ["worktree", "add"]
    if create_branch:
        args += ["-b", branch]
    args += [str(worktree_path)]
    if not create_branch:
        args.append(branch)
    else:
        args.append(base_branch)
    return run_git(args, cwd=repo_path)


def worktree_list(repo_path: str | Path) -> list[WorktreeInfo]:
    """List all worktrees in porcelain format."""
    output = run_git(["worktree", "list", "--porcelain"], cwd=repo_path)
    worktrees = []
    current: dict = {}

    for line in output.split("\n"):
        if not line:
            if current:
                worktrees.append(
                    WorktreeInfo(
                        path=current.get("worktree", ""),
                        branch=current.get("branch", "").replace("refs/heads/", ""),
                        head=current.get("HEAD", ""),
                        is_bare=current.get("bare", False),
                    )
                )
                current = {}
            continue

        if line.startswith("worktree "):
            current["worktree"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            current["HEAD"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line == "bare":
            current["bare"] = True

    if current:
        worktrees.append(
            WorktreeInfo(
                path=current.get("worktree", ""),
                branch=current.get("branch", "").replace("refs/heads/", ""),
                head=current.get("HEAD", ""),
                is_bare=current.get("bare", False),
            )
        )

    return worktrees


def worktree_remove(repo_path: str | Path, worktree_path: str | Path, force: bool = False) -> str:
    """Remove a git worktree."""
    args = ["worktree", "remove", str(worktree_path)]
    if force:
        args.append("--force")
    return run_git(args, cwd=repo_path)


def branch_exists(repo_path: str | Path, branch: str) -> bool:
    """Check if a branch exists."""
    try:
        run_git(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=repo_path)
        return True
    except GitError:
        return False


def delete_branch(repo_path: str | Path, branch: str, force: bool = False) -> str:
    """Delete a branch."""
    flag = "-D" if force else "-d"
    return run_git(["branch", flag, branch], cwd=repo_path)


def get_status(cwd: str | Path) -> str:
    """Get git status of a working directory."""
    return run_git(["status", "--short"], cwd=cwd)


def get_current_branch(cwd: str | Path) -> str:
    """Get the current branch name."""
    return run_git(["branch", "--show-current"], cwd=cwd)
