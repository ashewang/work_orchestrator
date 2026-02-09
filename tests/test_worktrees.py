"""Tests for git worktree operations."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import worktrees as worktrees_mod
from work_orchestrator.db.engine import init_db
from work_orchestrator.integrations.git import GitError, worktree_list


@pytest.fixture
def git_repo():
    """Create a temporary git repo with an initial commit."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmp, capture_output=True, check=True)
        # Create initial commit
        readme = Path(tmp) / "README.md"
        readme.write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp,
            capture_output=True,
            check=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        yield tmp


@pytest.fixture
def db(git_repo):
    """Create a temp DB linked to the git repo."""
    db_path = Path(git_repo) / "test.db"
    conn = init_db(db_path)
    projects_mod.create_project(conn, "test", "Test", git_repo)
    yield conn
    conn.close()


class TestWorktreeLifecycle:
    def test_create_worktree(self, db, git_repo):
        tasks_mod.create_task(db, "My feature", "test")
        result = worktrees_mod.create_worktree_for_task(db, "my-feature", git_repo)
        assert result["task_id"] == "my-feature"
        assert result["branch"] == "task/my-feature"
        assert Path(result["worktree_path"]).exists()
        assert not result["already_existed"]

    def test_create_worktree_idempotent(self, db, git_repo):
        tasks_mod.create_task(db, "Idem task", "test")
        r1 = worktrees_mod.create_worktree_for_task(db, "idem-task", git_repo)
        r2 = worktrees_mod.create_worktree_for_task(db, "idem-task", git_repo)
        assert r2["already_existed"] is True
        assert r1["worktree_path"] == r2["worktree_path"]

    def test_remove_worktree(self, db, git_repo):
        tasks_mod.create_task(db, "Remove me", "test")
        worktrees_mod.create_worktree_for_task(db, "remove-me", git_repo)
        result = worktrees_mod.remove_worktree_for_task(db, "remove-me", git_repo)
        assert result["removed"] is True

        task = tasks_mod.get_task(db, "remove-me")
        assert task.worktree_path is None

    def test_remove_no_worktree(self, db, git_repo):
        tasks_mod.create_task(db, "No wt", "test")
        result = worktrees_mod.remove_worktree_for_task(db, "no-wt", git_repo)
        assert result["removed"] is False

    def test_list_worktrees(self, db, git_repo):
        tasks_mod.create_task(db, "List test", "test")
        worktrees_mod.create_worktree_for_task(db, "list-test", git_repo)
        wts = worktrees_mod.list_task_worktrees(db, git_repo)
        task_wts = [w for w in wts if w.get("task_id") == "list-test"]
        assert len(task_wts) == 1
        assert task_wts[0]["branch"] == "task/list-test"

    def test_worktree_status(self, db, git_repo):
        tasks_mod.create_task(db, "Status check", "test")
        worktrees_mod.create_worktree_for_task(db, "status-check", git_repo)
        result = worktrees_mod.get_worktree_status(db, "status-check")
        assert "status" in result
        assert result["branch"] == "task/status-check"

    def test_cleanup_done_worktrees(self, db, git_repo):
        tasks_mod.create_task(db, "Cleanup test", "test")
        worktrees_mod.create_worktree_for_task(db, "cleanup-test", git_repo)
        tasks_mod.update_task_status(db, "cleanup-test", "done")

        results = worktrees_mod.cleanup_done_worktrees(db, git_repo, "test")
        assert len(results) == 1
        assert results[0]["removed"] is True


class TestWorktreeErrors:
    def test_create_for_nonexistent_task(self, db, git_repo):
        with pytest.raises(ValueError, match="Task not found"):
            worktrees_mod.create_worktree_for_task(db, "nope", git_repo)

    def test_status_for_nonexistent_task(self, db, git_repo):
        with pytest.raises(ValueError, match="Task not found"):
            worktrees_mod.get_worktree_status(db, "nope")
