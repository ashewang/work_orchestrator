"""Tests for the CLI."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from work_orchestrator.cli import main
from work_orchestrator.db.engine import init_db
from work_orchestrator.core import projects as projects_mod


@pytest.fixture
def cli_env():
    """Set up a temp environment for CLI testing."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        repo_path = Path(tmp) / "repo"
        repo_path.mkdir()

        # Init git repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_path, capture_output=True, check=True)
        (repo_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )

        env = {
            "WO_DB_PATH": str(db_path),
            "WO_REPO_PATH": str(repo_path),
        }
        old_env = {}
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

        yield CliRunner(), str(repo_path)

        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestCLI:
    def test_help(self, cli_env):
        runner, _ = cli_env
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Work Orchestrator" in result.output

    def test_init_and_task_flow(self, cli_env):
        runner, repo_path = cli_env

        # Init project
        result = runner.invoke(main, ["init", "my-project", "--repo-path", repo_path])
        assert result.exit_code == 0
        assert "my-project" in result.output

        # Add task
        result = runner.invoke(main, ["task", "add", "Test task", "--project", "my-project"])
        assert result.exit_code == 0
        assert "test-task" in result.output

        # List tasks
        result = runner.invoke(main, ["task", "list", "--project", "my-project"])
        assert result.exit_code == 0
        assert "test-task" in result.output
        assert "todo" in result.output

        # Show task
        result = runner.invoke(main, ["task", "show", "test-task"])
        assert result.exit_code == 0
        assert "Test task" in result.output

    def test_memory_flow(self, cli_env):
        runner, _ = cli_env

        # Set memory
        result = runner.invoke(main, ["memory", "set", "test-key", "test-value"])
        assert result.exit_code == 0

        # Get memory
        result = runner.invoke(main, ["memory", "get", "test-key"])
        assert result.exit_code == 0
        assert "test-value" in result.output

        # List memories
        result = runner.invoke(main, ["memory", "list"])
        assert result.exit_code == 0
        assert "test-key" in result.output

    def test_task_start_creates_worktree(self, cli_env):
        runner, repo_path = cli_env

        runner.invoke(main, ["init", "wt-test", "--repo-path", repo_path])
        runner.invoke(main, ["task", "add", "Worktree task", "--project", "wt-test"])

        result = runner.invoke(main, ["task", "start", "worktree-task"])
        assert result.exit_code == 0
        assert "Worktree" in result.output or "task/worktree-task" in result.output

    def test_task_done_removes_worktree(self, cli_env):
        runner, repo_path = cli_env

        runner.invoke(main, ["init", "done-test", "--repo-path", repo_path])
        runner.invoke(main, ["task", "add", "Done task", "--project", "done-test"])
        runner.invoke(main, ["task", "start", "done-task"])

        result = runner.invoke(main, ["task", "done", "done-task"])
        assert result.exit_code == 0
        assert "Completed" in result.output
