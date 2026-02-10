"""Tests for agent orchestration."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from work_orchestrator.core import agents as agents_mod
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.db.engine import init_db


@pytest.fixture
def git_repo():
    """Create a temporary git repo with multiple worktrees."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        }
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "main"], cwd=repo, capture_output=True, check=True
        )
        (repo / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo, capture_output=True, check=True, env=env,
        )
        # Create two additional worktrees
        wt1 = Path(tmp) / "wt-alpha"
        wt2 = Path(tmp) / "wt-beta"
        subprocess.run(
            ["git", "worktree", "add", "-b", "alpha", str(wt1), "main"],
            cwd=repo, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "-b", "beta", str(wt2), "main"],
            cwd=repo, capture_output=True, check=True,
        )
        yield str(repo), tmp


@pytest.fixture
def db(git_repo):
    repo_path, tmp = git_repo
    db_path = Path(tmp) / "test.db"
    conn = init_db(db_path)
    projects_mod.create_project(conn, "test", "Test Project", repo_path)
    yield conn
    conn.close()


@pytest.fixture
def db_with_slots(db, git_repo):
    """DB with worktree slots already registered (no subprocess mocking needed)."""
    repo_path, _ = git_repo
    agents_mod.discover_and_register_worktrees(db, "test", repo_path)
    return db


class TestWorktreeSlots:
    def test_discover_worktrees(self, db, git_repo):
        repo_path, _ = git_repo
        slots = agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        # Should find main + 2 additional = 3 worktrees
        assert len(slots) == 3
        labels = {s.label for s in slots}
        assert "wt-alpha" in labels
        assert "wt-beta" in labels

    def test_discover_idempotent(self, db, git_repo):
        repo_path, _ = git_repo
        agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        slots2 = agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        assert len(slots2) == 0  # No new ones

    def test_list_slots(self, db, git_repo):
        repo_path, _ = git_repo
        agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        all_slots = agents_mod.list_worktree_slots(db, "test")
        assert len(all_slots) == 3
        avail = agents_mod.list_worktree_slots(db, "test", status="available")
        assert len(avail) == 3

    def test_get_slot_by_label(self, db, git_repo):
        repo_path, _ = git_repo
        agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        slot = agents_mod.get_slot_by_label(db, "test", "wt-alpha")
        assert slot is not None
        assert slot.label == "wt-alpha"
        assert slot.branch == "alpha"

    def test_assign_and_release(self, db, git_repo):
        repo_path, _ = git_repo
        agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Test task", "test")

        assigned = agents_mod.assign_task_to_slot(db, task.id, slots[0].id)
        assert assigned.status == "occupied"
        assert assigned.current_task_id == task.id

        # Task should have worktree_path set
        updated_task = tasks_mod.get_task(db, task.id)
        assert updated_task.worktree_path == slots[0].path

        released = agents_mod.release_slot(db, slots[0].id)
        assert released.status == "available"
        assert released.current_task_id is None

    def test_assign_occupied_slot_fails(self, db, git_repo):
        repo_path, _ = git_repo
        agents_mod.discover_and_register_worktrees(db, "test", repo_path)
        slots = agents_mod.list_worktree_slots(db, "test")
        t1 = tasks_mod.create_task(db, "Task 1", "test")
        t2 = tasks_mod.create_task(db, "Task 2", "test")

        agents_mod.assign_task_to_slot(db, t1.id, slots[0].id)
        with pytest.raises(ValueError, match="already occupied"):
            agents_mod.assign_task_to_slot(db, t2.id, slots[0].id)

    def test_register_single_slot(self, db, git_repo):
        _, tmp = git_repo
        slot = agents_mod.register_worktree_slot(
            db, "test", "/some/path", "custom-slot", "feature-branch"
        )
        assert slot.label == "custom-slot"
        assert slot.branch == "feature-branch"
        assert slot.status == "available"


class TestPromptBuilder:
    def test_build_prompt(self, db, git_repo):
        tasks_mod.create_task(db, "Implement auth", "test", description="Add JWT auth")
        prompt = agents_mod.build_agent_prompt(db, "implement-auth", "Add login endpoint")
        assert "Implement auth" in prompt
        assert "Add JWT auth" in prompt
        assert "Add login endpoint" in prompt
        assert "Completion" in prompt

    def test_build_prompt_with_project_context(self, db, git_repo):
        tasks_mod.create_task(db, "Fix bug", "test")
        prompt = agents_mod.build_agent_prompt(db, "fix-bug", "Fix the bug")
        assert "Test Project" in prompt

    def test_build_prompt_nonexistent_task(self, db, git_repo):
        with pytest.raises(ValueError, match="Task not found"):
            agents_mod.build_agent_prompt(db, "nope", "instructions")


class TestAgentLaunch:
    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_launch_agent(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Launch test", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        run = agents_mod.launch_agent(
            db, task.id, "Do the thing",
            output_dir=str(Path(tmp) / "outputs"),
            model="sonnet",
        )
        assert run.pid == 12345
        assert run.status == "running"
        assert run.task_id == task.id
        assert run.model == "sonnet"
        mock_popen.assert_called_once()

        # Task should be moved to in-progress
        updated = tasks_mod.get_task(db, task.id)
        assert updated.status == "in-progress"

    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_launch_without_slot_fails(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        task = tasks_mod.create_task(db, "No slot", "test")
        with pytest.raises(ValueError, match="not assigned"):
            agents_mod.launch_agent(
                db, task.id, "instructions",
                output_dir=str(Path(tmp) / "outputs"),
            )

    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_double_launch_fails(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Double launch", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 11111
        mock_popen.return_value = mock_proc

        agents_mod.launch_agent(
            db, task.id, "First",
            output_dir=str(Path(tmp) / "outputs"),
        )
        with pytest.raises(ValueError, match="already has a running agent"):
            agents_mod.launch_agent(
                db, task.id, "Second",
                output_dir=str(Path(tmp) / "outputs"),
            )


class TestAgentCancel:
    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_cancel_agent(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Cancel test", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc

        agents_mod.launch_agent(
            db, task.id, "Work on this",
            output_dir=str(Path(tmp) / "outputs"),
        )

        with patch("os.kill") as mock_kill:
            cancelled = agents_mod.cancel_agent(db, task.id)
            assert cancelled.status == "cancelled"
            mock_kill.assert_called_once_with(99999, 15)  # SIGTERM

        # Slot should be released
        slot = agents_mod.get_worktree_slot(db, slots[0].id)
        assert slot.status == "available"

    def test_cancel_nonexistent(self, db, git_repo):
        result = agents_mod.cancel_agent(db, "nope")
        assert result is None


class TestAgentQueries:
    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_get_latest_run(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Query test", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 55555
        mock_popen.return_value = mock_proc

        agents_mod.launch_agent(
            db, task.id, "Do stuff",
            output_dir=str(Path(tmp) / "outputs"),
        )

        run = agents_mod.get_latest_agent_run(db, task.id)
        assert run is not None
        assert run.pid == 55555

    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_list_agent_runs(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "List test", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 77777
        mock_popen.return_value = mock_proc

        agents_mod.launch_agent(
            db, task.id, "Work",
            output_dir=str(Path(tmp) / "outputs"),
        )

        runs = agents_mod.list_agent_runs(db, status="running")
        assert len(runs) == 1
        assert runs[0].task_id == task.id

        runs_by_project = agents_mod.list_agent_runs(db, project_id="test")
        assert len(runs_by_project) == 1

    def test_get_output_no_run(self, db, git_repo):
        output = agents_mod.get_agent_output(db, "nope")
        assert output is None


class TestDelegateTask:
    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_delegate_auto_picks_slot(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        task = tasks_mod.create_task(db, "Delegate test", "test")

        mock_proc = MagicMock()
        mock_proc.pid = 44444
        mock_popen.return_value = mock_proc

        run = agents_mod.delegate_task(
            db, task.id, "Do the work",
            output_dir=str(Path(tmp) / "outputs"),
            model="sonnet",
            max_turns=10,
        )
        assert run.pid == 44444
        assert run.status == "running"

        # Task should be assigned to a slot and in-progress
        updated_task = tasks_mod.get_task(db, task.id)
        assert updated_task.status == "in-progress"
        assert updated_task.worktree_path is not None

    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_delegate_specific_slot(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        task = tasks_mod.create_task(db, "Specific slot", "test")

        mock_proc = MagicMock()
        mock_proc.pid = 33333
        mock_popen.return_value = mock_proc

        run = agents_mod.delegate_task(
            db, task.id, "Work on alpha",
            output_dir=str(Path(tmp) / "outputs"),
            slot_label="wt-alpha",
        )
        assert run.pid == 33333

        slot = agents_mod.get_slot_by_label(db, "test", "wt-alpha")
        assert slot.status == "occupied"
        assert slot.current_task_id == task.id

    def test_delegate_no_slots_available(self, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        # Occupy all slots
        slots = agents_mod.list_worktree_slots(db, "test")
        for i, slot in enumerate(slots):
            t = tasks_mod.create_task(db, f"Filler {i}", "test")
            agents_mod.assign_task_to_slot(db, t.id, slot.id)

        # Now try to delegate a new task
        task = tasks_mod.create_task(db, "No slots left", "test")
        with pytest.raises(ValueError, match="No available worktree slots"):
            agents_mod.delegate_task(
                db, task.id, "Do something",
                output_dir=str(Path(tmp) / "outputs"),
            )

    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_delegate_already_running_fails(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        task = tasks_mod.create_task(db, "Double delegate", "test")

        mock_proc = MagicMock()
        mock_proc.pid = 22222
        mock_popen.return_value = mock_proc

        agents_mod.delegate_task(
            db, task.id, "First run",
            output_dir=str(Path(tmp) / "outputs"),
        )
        with pytest.raises(ValueError, match="already has a running agent"):
            agents_mod.delegate_task(
                db, task.id, "Second run",
                output_dir=str(Path(tmp) / "outputs"),
            )

    def test_delegate_nonexistent_task(self, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        with pytest.raises(ValueError, match="Task not found"):
            agents_mod.delegate_task(
                db, "nonexistent", "instructions",
                output_dir=str(Path(tmp) / "outputs"),
            )


class TestLaunchWithMaxTurns:
    @patch("work_orchestrator.core.agents.subprocess.Popen")
    def test_max_turns_and_mcp_config_passed(self, mock_popen, db_with_slots, git_repo):
        _, tmp = git_repo
        db = db_with_slots
        slots = agents_mod.list_worktree_slots(db, "test")
        task = tasks_mod.create_task(db, "Max turns test", "test")
        agents_mod.assign_task_to_slot(db, task.id, slots[0].id)

        mock_proc = MagicMock()
        mock_proc.pid = 88888
        mock_popen.return_value = mock_proc

        run = agents_mod.launch_agent(
            db, task.id, "Do multi-step work",
            output_dir=str(Path(tmp) / "outputs"),
            model="sonnet",
            max_turns=30,
            mcp_config_path="/path/to/.mcp.json",
        )
        assert run.pid == 88888

        # Verify the command includes --max-turns and --mcp-config
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert "--max-turns" in cmd
        assert "30" in cmd
        assert "--mcp-config" in cmd
        assert "/path/to/.mcp.json" in cmd


class TestReviewStatus:
    def test_review_status_accepted(self, db, git_repo):
        """Test that 'review' is a valid task status."""
        task = tasks_mod.create_task(db, "Review me", "test")
        updated = tasks_mod.update_task_status(db, task.id, "review")
        assert updated.status == "review"
