"""Git worktree lifecycle management tied to tasks."""

import sqlite3
from pathlib import Path

from work_orchestrator.core.tasks import get_task, _log_event
import logging

from work_orchestrator.integrations.git import (
    GitError,
    WorktreeInfo,
    branch_exists,
    delete_branch,
    run_git,
    worktree_add,
    worktree_list,
    worktree_remove,
    get_status,
)

logger = logging.getLogger(__name__)


def create_worktree_for_task(
    db: sqlite3.Connection,
    task_id: str,
    repo_path: str | Path,
    worktree_base_dir: str = ".worktrees",
    base_branch: str = "main",
    branch_name: str | None = None,
) -> dict:
    """Create a git worktree for a task. Returns worktree info dict."""
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    if task.worktree_path:
        wt_path = Path(task.worktree_path)
        if wt_path.exists():
            return {
                "task_id": task_id,
                "worktree_path": str(wt_path),
                "branch": task.branch_name,
                "already_existed": True,
            }

    repo = Path(repo_path)
    if branch_name is None:
        branch_name = f"task/{task_id}"

    wt_path = repo / worktree_base_dir / f"task-{task_id}"

    create_branch = not branch_exists(repo, branch_name)
    worktree_add(repo, wt_path, branch_name, base_branch, create_branch=create_branch)

    db.execute(
        "UPDATE tasks SET branch_name = ?, worktree_path = ?, updated_at = datetime('now') WHERE id = ?",
        (branch_name, str(wt_path), task_id),
    )
    _log_event(db, task_id, "worktree_created", None, str(wt_path))
    db.commit()

    return {
        "task_id": task_id,
        "worktree_path": str(wt_path),
        "branch": branch_name,
        "already_existed": False,
    }


def remove_worktree_for_task(
    db: sqlite3.Connection,
    task_id: str,
    repo_path: str | Path,
    force: bool = False,
    delete_branch_after: bool = False,
) -> dict:
    """Remove the worktree for a task."""
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    if not task.worktree_path:
        return {"task_id": task_id, "removed": False, "reason": "No worktree assigned"}

    wt_path = Path(task.worktree_path)
    branch = task.branch_name
    repo = Path(repo_path)

    if wt_path.exists():
        try:
            worktree_remove(repo, wt_path, force=force)
        except GitError as e:
            if not force:
                return {"task_id": task_id, "removed": False, "reason": str(e)}
            raise

    if delete_branch_after and branch and branch_exists(repo, branch):
        try:
            delete_branch(repo, branch, force=force)
        except GitError:
            pass  # Branch deletion is best-effort

    db.execute(
        "UPDATE tasks SET worktree_path = NULL, updated_at = datetime('now') WHERE id = ?",
        (task_id,),
    )
    _log_event(db, task_id, "worktree_removed", str(wt_path), None)
    db.commit()

    return {"task_id": task_id, "removed": True, "path": str(wt_path)}


def list_task_worktrees(
    db: sqlite3.Connection,
    repo_path: str | Path,
) -> list[dict]:
    """List all worktrees and match them to tasks."""
    git_worktrees = worktree_list(repo_path)
    task_rows = db.execute(
        "SELECT id, title, status, branch_name, worktree_path FROM tasks WHERE worktree_path IS NOT NULL"
    ).fetchall()

    # Use resolved paths for comparison (handles macOS /private symlinks etc.)
    task_by_path = {}
    for row in task_rows:
        resolved = str(Path(row["worktree_path"]).resolve())
        task_by_path[resolved] = dict(row)

    result = []
    for wt in git_worktrees:
        entry = {
            "path": wt.path,
            "branch": wt.branch,
            "head": wt.head,
        }
        resolved_wt = str(Path(wt.path).resolve())
        task_info = task_by_path.get(resolved_wt)
        if task_info:
            entry["task_id"] = task_info["id"]
            entry["task_title"] = task_info["title"]
            entry["task_status"] = task_info["status"]
        result.append(entry)

    return result


def get_worktree_status(
    db: sqlite3.Connection,
    task_id: str,
) -> dict:
    """Get git status for a task's worktree."""
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")
    if not task.worktree_path:
        return {"task_id": task_id, "error": "No worktree assigned"}

    wt_path = Path(task.worktree_path)
    if not wt_path.exists():
        return {"task_id": task_id, "error": f"Worktree path does not exist: {wt_path}"}

    status = get_status(wt_path)
    return {
        "task_id": task_id,
        "worktree_path": str(wt_path),
        "branch": task.branch_name,
        "status": status if status else "(clean)",
    }


def cleanup_done_worktrees(
    db: sqlite3.Connection,
    repo_path: str | Path,
    project_id: str = "default",
    recycle: bool = False,
) -> list[dict]:
    """Remove (or recycle) worktrees for all completed tasks in a project.

    If recycle=True, resets the worktree branch instead of removing it,
    leaving the slot ready for reuse without recreating the worktree.
    """
    tasks = db.execute(
        "SELECT id FROM tasks WHERE project_id = ? AND status = 'done' AND worktree_path IS NOT NULL",
        (project_id,),
    ).fetchall()

    results = []
    for row in tasks:
        if recycle:
            result = recycle_worktree(db, row["id"], repo_path)
        else:
            result = remove_worktree_for_task(db, row["id"], repo_path)
        results.append(result)
    return results


def recycle_worktree(
    db: sqlite3.Connection,
    task_id: str,
    repo_path: str | Path,
    base_branch: str = "main",
) -> dict:
    """Recycle a worktree: reset it to base branch so the slot can be reused.

    Instead of removing the worktree, this resets the branch to the base branch,
    cleans untracked files, and clears the task association. The worktree directory
    stays in place, avoiding the cost of re-creating it.

    Flow: checkout base → reset --hard → clean -fd → clear task worktree_path
    """
    task = get_task(db, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    if not task.worktree_path:
        return {"task_id": task_id, "recycled": False, "reason": "No worktree assigned"}

    wt_path = Path(task.worktree_path)
    if not wt_path.exists():
        return {"task_id": task_id, "recycled": False, "reason": "Worktree path does not exist"}

    try:
        # Reset the worktree to a clean state
        run_git(["checkout", base_branch], cwd=wt_path)
        run_git(["reset", "--hard", f"origin/{base_branch}"], cwd=wt_path)
        run_git(["clean", "-fd"], cwd=wt_path)
    except GitError:
        # Fallback: try without origin/ prefix (local-only repos)
        try:
            run_git(["checkout", base_branch], cwd=wt_path)
            run_git(["reset", "--hard", base_branch], cwd=wt_path)
            run_git(["clean", "-fd"], cwd=wt_path)
        except GitError as e:
            logger.warning("Failed to recycle worktree for %s: %s", task_id, e)
            return {"task_id": task_id, "recycled": False, "reason": str(e)}

    # Clear the task's worktree association
    db.execute(
        "UPDATE tasks SET worktree_path = NULL, updated_at = datetime('now') WHERE id = ?",
        (task_id,),
    )
    _log_event(db, task_id, "worktree_recycled", str(wt_path), None)
    db.commit()

    return {"task_id": task_id, "recycled": True, "path": str(wt_path)}
